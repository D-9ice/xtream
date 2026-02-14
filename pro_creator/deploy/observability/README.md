# Observability Stack

This folder contains baseline observability configs for production:

- `prometheus/prometheus.yml`: scrape targets and alerting config
- `prometheus/alerts.yml`: starter alert rules
- `alertmanager/alertmanager.yml`: local alert routing
- `grafana/provisioning/*`: datasource and dashboard provisioning

Enable the stack with:

```zsh
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile observability up -d --build
```

Default local endpoints:

- Prometheus: `http://127.0.0.1:9090`
- Alertmanager: `http://127.0.0.1:9093`
- Grafana: `http://127.0.0.1:3001`
