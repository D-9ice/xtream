# Rhubarb Binary Placement (Production)

Place the `rhubarb` binary in this folder on your server:

- `pro_creator/deploy/bin/rhubarb`

In production compose, `./deploy` is mounted into the container at `/app/deploy`,
so the default path in `.env.production` can be:

- `RHUBARB_PATH=/app/deploy/bin/rhubarb`

Ensure the file is executable:

```sh
chmod +x deploy/bin/rhubarb
```

