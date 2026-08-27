from django.db import migrations, models


def normalize_existing_logs(apps, _schema_editor):
    AuditLog = apps.get_model("monitoring", "AuditLog")
    mapping = {
        ("CREATE", "accounts.User"): "USER_CREATED",
        ("UPDATE", "accounts.User"): "USER_UPDATED",
        ("DELETE", "accounts.User"): "USER_DELETED",
        ("CREATE", "inventory.Machine"): "MACHINE_CREATED",
        ("UPDATE", "inventory.Machine"): "MACHINE_UPDATED",
        ("DELETE", "inventory.Machine"): "MACHINE_DELETED",
        ("ML_TRAINING_QUEUED", "ml_engine.MLModelVersion"): "MODEL_TRAINING_QUEUED",
        ("ML_EVALUATION_QUEUED", "ml_engine.MLModelVersion"): "MODEL_EVALUATION_QUEUED",
    }
    for log in AuditLog.objects.select_related("actor").iterator():
        updates = {
            "actor_email": getattr(log.actor, "email", "") or "",
            "target_repr": f"{log.target_type}:{log.target_id}".strip(":"),
        }
        action = mapping.get((log.action, log.target_type))
        if action:
            updates["action"] = action
        elif log.action in {"CREATE", "UPDATE", "DELETE", "MONITORING_RULE_TOGGLED"}:
            updates["action"] = "CONFIG_CHANGED"
        AuditLog.objects.filter(pk=log.pk).update(**updates)


def remove_mutation_permissions(apps, _schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(
        content_type__app_label="monitoring",
        content_type__model="auditlog",
        codename__in=["change_auditlog", "delete_auditlog"],
    ).delete()


APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION monitoring_protect_audit_log()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit logs are append-only' USING ERRCODE = '55000';
    END IF;
    IF (to_jsonb(NEW) - 'actor_id' - 'customer_id')
       IS DISTINCT FROM (to_jsonb(OLD) - 'actor_id' - 'customer_id') THEN
        RAISE EXCEPTION 'audit logs are append-only' USING ERRCODE = '55000';
    END IF;
    IF NEW.actor_id IS DISTINCT FROM OLD.actor_id
       AND NOT (OLD.actor_id IS NOT NULL AND NEW.actor_id IS NULL) THEN
        RAISE EXCEPTION 'audit actor cannot be changed' USING ERRCODE = '55000';
    END IF;
    IF NEW.customer_id IS DISTINCT FROM OLD.customer_id
       AND NOT (OLD.customer_id IS NOT NULL AND NEW.customer_id IS NULL) THEN
        RAISE EXCEPTION 'audit customer cannot be changed' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER monitoring_audit_log_append_only
BEFORE UPDATE OR DELETE ON monitoring_auditlog
FOR EACH ROW EXECUTE FUNCTION monitoring_protect_audit_log();
"""

REVERSE_APPEND_ONLY_SQL = """
DROP TRIGGER IF EXISTS monitoring_audit_log_append_only ON monitoring_auditlog;
DROP FUNCTION IF EXISTS monitoring_protect_audit_log();
"""


class Migration(migrations.Migration):
    dependencies = [("monitoring", "0004_anomaly_window_start_and_more")]

    operations = [
        migrations.RenameField(
            model_name="auditlog", old_name="context", new_name="metadata"
        ),
        migrations.RenameField(
            model_name="auditlog", old_name="created_at", new_name="timestamp"
        ),
        migrations.AddField(
            model_name="auditlog",
            name="actor_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="ip_address",
            field=models.GenericIPAddressField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="target_repr",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(db_index=True, max_length=120),
        ),
        migrations.AlterModelOptions(
            name="auditlog",
            options={
                "default_permissions": ("add", "view"),
                "ordering": ["-timestamp", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["customer", "timestamp"], name="monitoring__custome_89ae5a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["customer", "action", "timestamp"],
                name="monitoring__custome_1dfd79_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["actor", "timestamp"], name="monitoring__actor_i_033144_idx"
            ),
        ),
        migrations.RunPython(normalize_existing_logs, migrations.RunPython.noop),
        migrations.RunPython(remove_mutation_permissions, migrations.RunPython.noop),
        migrations.RunSQL(APPEND_ONLY_SQL, REVERSE_APPEND_ONLY_SQL),
    ]
