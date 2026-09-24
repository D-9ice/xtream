# File-Based Secrets

Store production secrets as files and point environment variables to them using `*_FILE`.

Example `.env.production` entries:

```dotenv
JWT_SECRET_FILE=./deploy/secrets/jwt_secret
ADMIN_PASSWORD_FILE=./deploy/secrets/admin_password
POSTGRES_PASSWORD_FILE=./deploy/secrets/postgres_password
DATABASE_URL_FILE=./deploy/secrets/database_url
S3_SECRET_KEY_FILE=./deploy/secrets/s3_secret_key
```

Create each file with the raw secret value only (no key/value syntax).

Do not commit secret files.

## AWS Secrets Manager

You can also resolve secrets from AWS Secrets Manager.

Enable in `.env.production`:

```dotenv
AWS_SECRETS_ENABLED=true
AWS_SECRETS_REGION=us-east-1
```

Per-variable mapping:

```dotenv
JWT_SECRET_AWS_SECRET_ID=pro-creator/prod/jwt
JWT_SECRET_AWS_SECRET_KEY=jwt_secret
```

If your naming convention is consistent, set a prefix and omit per-variable IDs:

```dotenv
AWS_SECRET_PREFIX=pro-creator/prod
```

With the prefix above, `JWT_SECRET` resolves from secret id:
`pro-creator/prod/jwt_secret`
