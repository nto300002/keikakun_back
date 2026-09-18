#!/bin/sh

set -eu

project_id="${1:?PROJECT_ID is required}"

while IFS='=' read -r env_name reference; do
  secret_id=${reference%:*}
  version=${reference##*:}
  state=$(gcloud secrets versions describe "$version" \
    --secret="$secret_id" \
    --project="$project_id" \
    --format='value(state)')

  if [ "$state" != "ENABLED" ]; then
    printf 'FAIL secret metadata: %s: version %s is %s\n' "$env_name" "$version" "$state" >&2
    exit 1
  fi
  printf 'PASS secret metadata: %s\n' "$env_name"
done <<'SECRET_REFERENCES'
DATABASE_URL=prod-database-url:1
SECRET_KEY=prod-secret-key:1
ENCRYPTION_KEY=prod-encryption-key:1
AWS_ACCESS_KEY_ID=prod-aws-access-key-id:1
AWS_SECRET_ACCESS_KEY=prod-aws-secret-access-key:1
S3_ACCESS_KEY=prod-s3-access-key:1
S3_SECRET_KEY=prod-s3-secret-key:1
MAIL_USERNAME=prod-mail-username:1
MAIL_PASSWORD=prod-mail-password:1
STRIPE_SECRET_KEY=prod-stripe-secret-key:2
STRIPE_WEBHOOK_SECRET=prod-stripe-webhook-secret:1
VAPID_PRIVATE_KEY=prod-vapid-private-key:1
CALENDAR_ENCRYPTION_KEY=prod-calendar-encryption-key:1
SECRET_REFERENCES
