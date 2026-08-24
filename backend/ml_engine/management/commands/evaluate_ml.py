import json
from django.core.management.base import BaseCommand, CommandError
from ml_engine.evaluation import evaluate_detection_strategies


class Command(BaseCommand):
    help = "Compare Rules/ML/Hybrid sur les événements réels persistés."

    def add_arguments(self, parser):
        parser.add_argument("customer_id")
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        if not 1 <= options["days"] <= 3650:
            raise CommandError("--days doit être compris entre 1 et 3650.")
        result = evaluate_detection_strategies(
            options["customer_id"], days=options["days"]
        )
        self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False))
