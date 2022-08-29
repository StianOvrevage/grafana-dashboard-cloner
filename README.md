# grafana-dashboard-cloner
Tool that clones dashboard from one grafana instance to another based on tags.

Keeping dashboards in sync between Grafana instances can be a real PITA and dashboards-as-code
doesn't really work in practice.


## Known issues

I have sometimes seen 403 Access Denied when trying to fetch the dashboard to be updated from the destination Grafana
instance if the dashboard is in the `General` folder or has been moved around in the destination.

## Preparation

Create API keys with the Editor role in both environments. You need to be Admin in Grafana to do that.

## Usage

The configurations `GRAFANA_SOURCE_APIKEY`, `GRAFANA_DESTINATION_APIKEY`, `GRAFANA_SOURCE_URL` and `GRAFANA_DESTINATION_URL` should be self-explanatory ;)

- `DASHBOARD_SOURCE_CLONE_TAG` - Dashboards in the source Grafana instance with this tag will be cloned
- `DASHBOARD_DESTINATION_CLONE_TAG` - Dashboards that are cloned will have this tag added in the destination Grafana instance

### Local

    export GRAFANA_SOURCE_APIKEY=x
    export GRAFANA_DESTINATION_APIKEY=x

    export GRAFANA_SOURCE_URL=https://grafana.dev.example.com
    export GRAFANA_DESTINATION_URL=https://grafana.example.com

    export DASHBOARD_SOURCE_CLONE_TAG=clone-from-dev
    export DASHBOARD_DESTINATION_CLONE_TAG=cloned-from-dev

    pip3 install -r requirements.txt
    python3 grafana-dashboard-cloner.py

### Docker

    docker run -e GRAFANA_SOURCE_APIKEY=xx \
              -e GRAFANA_DESTINATION_APIKEY=xx \
              -e GRAFANA_SOURCE_URL=https://grafana.dev.example.com \
              -e GRAFANA_DESTINATION_URL=https://grafana.example.com \
              -e DASHBOARD_SOURCE_CLONE_TAG=clone-from-dev \
              -e DASHBOARD_DESTINATION_CLONE_TAG=cloned-from-dev \
      stianovrevage/grafana-dashboard-cloner

### Kubernetes

  helm repo add grafana-dashboard-cloner 'https://raw.githubusercontent.com/StianOvrevage/grafana-dashboard-cloner/main/chart/'
  helm repo update

  kubectl create namespace grafana-dashboard-cloner
  helm upgrade --install --namespace=grafana-dashboard-cloner grafana-dashboard-cloner grafana-dashboard-cloner/grafana-dashboard-cloner --values my-values-file.yaml

# Features

### Daemon mode

In daemon mode (`--daemon=true`) the tool executes a sync every `--daemon-sync-interval-sec` seconds (default 300) and sleeps in between.

The benefit of this is that we can keep track of which dashboards have changed on both sides and only clone when necessary.

In non-daemon mode all matching dashboards will be cloned every time.

The criteria for if a dashboard is to be cloned each interval is:
 - If there is a new `version` in the source dashboard
 - If the `editable` flag is true in the destination. This might mean someone has done changes and things are out of sync.
 - If the dashboard does not already exist in the destination Grafana

# Backlog

- Collect and count errors instead of exiting immediately
- Support Grafana Service Accounts: https://grafana.com/docs/grafana/latest/administration/service-accounts/
- Expose HTTP service with metrics

### Development: Updating helm chart

    cd chart/
    helm package grafana-dashboard-cloner/
    helm repo index .