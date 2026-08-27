import os
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email, validate_slug
from django.db import transaction
from django.utils.text import slugify

from accounts.models import Customer, User
from inventory.models import Environment
from monitoring.audit import record_audit
from monitoring.models import AuditLog


PASSWORD_ENV = "INFRASENTINEL_BOOTSTRAP_PASSWORD"


class Command(BaseCommand):
    help = (
        "Create the first local tenant administrator without enabling public "
        "registration or placing a password on the command line."
    )

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--customer-slug", default="")
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            help="Read one password line from stdin instead of the environment.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Print EXISTS or MISSING without changing the database.",
        )

    def handle(self, *args, **options):
        organization = str(options["organization"]).strip()
        email = str(options["email"]).strip().lower()
        if not organization or len(organization) > 160:
            raise CommandError("Organization must contain 1 to 160 characters.")
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("A valid administrator email is required.") from exc

        requested_slug = str(options["customer_slug"]).strip()
        customer_slug = requested_slug or slugify(organization)[:80]
        if not customer_slug or len(customer_slug) > 80:
            raise CommandError("Unable to derive a valid customer slug.")
        try:
            validate_slug(customer_slug)
        except ValidationError as exc:
            raise CommandError("The customer slug is invalid.") from exc

        existing_user = (
            User.objects.select_related("customer").filter(email=email).first()
        )
        if existing_user:
            if (
                existing_user.customer is None
                or existing_user.customer.slug != customer_slug
                or existing_user.role != User.Role.ADMIN
            ):
                raise CommandError(
                    "The email already belongs to a different tenant or role."
                )
            if options["check"]:
                self.stdout.write("EXISTS")
                return
            Environment.objects.get_or_create(
                customer=existing_user.customer,
                name="Windows",
                defaults={"kind": Environment.Kind.WINDOWS},
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Local administrator already exists; no password changed."
                )
            )
            return

        if options["check"]:
            self.stdout.write("MISSING")
            return

        if options["password_stdin"]:
            password = sys.stdin.readline().rstrip("\r\n")
        else:
            password = os.getenv(PASSWORD_ENV, "")
        if not password:
            raise CommandError(
                f"Provide the password through --password-stdin or {PASSWORD_ENV}."
            )

        candidate = User(username=email, email=email)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError("Password rejected: " + " ".join(exc.messages)) from exc

        with transaction.atomic():
            customer = Customer.objects.filter(slug=customer_slug).first()
            if customer and customer.name != organization:
                raise CommandError(
                    "The requested customer slug already belongs to another organization."
                )
            if customer is None:
                customer = Customer.objects.create(
                    name=organization, slug=customer_slug
                )
            environment, environment_created = Environment.objects.get_or_create(
                customer=customer,
                name="Windows",
                defaults={"kind": Environment.Kind.WINDOWS},
            )
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                customer=customer,
                role=User.Role.ADMIN,
                is_active=True,
            )
            record_audit(
                AuditLog.Action.USER_CREATED,
                customer=customer,
                actor=user,
                target=user,
                metadata={"source": "local_laptop_bootstrap", "role": user.role},
            )
            if environment_created:
                record_audit(
                    AuditLog.Action.CONFIG_CHANGED,
                    customer=customer,
                    actor=user,
                    target=environment,
                    metadata={
                        "source": "local_laptop_bootstrap",
                        "operation": "create",
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Local administrator created for tenant '{customer.slug}'."
            )
        )
