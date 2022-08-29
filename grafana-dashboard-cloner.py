import requests
import json_logging, logging, sys, os, time, argparse
import json

def main():
  logger.debug(f'Config: {args}')
  # start = time.time()

  grafana_source_headers = {'Authorization': 'Bearer ' + args.grafana_source_apikey}
  grafana_destination_headers = {'Authorization': 'Bearer ' + args.grafana_destination_apikey}

  source_dashboards = {}

  while(True):
    # Get mapping from destination folder names to folder ids so we can put dashboards in the same folder names
    try:
      r_destination_folders = requests.get(args.grafana_destination_url + '/api/folders', headers=grafana_destination_headers)
      r_destination_folders.raise_for_status()
    except requests.RequestException as err:
      logger.error(f'Could not fetch folders from destination grafana: {err}')
      sys.exit(1)

    destinationFolderIds = {}
    # Dashboards without folder information implicitly belongs in the "General" special root-level folder that has id 0
    destinationFolderIds["General"] = 0

    for folder in r_destination_folders.json():
      destinationFolderIds[folder['title']] = folder['id']

    logger.debug(destinationFolderIds)

    # Get dashboards with tag for copying
    try:
      r_source_dashboard_search = requests.get(args.grafana_source_url + '/api/search?tag=' + args.dashboard_source_clone_tag, headers=grafana_source_headers)
      r_source_dashboard_search.raise_for_status()
    except requests.RequestException as err:
      logger.error(f'Could not search dashboards from grafana source: {err}')
      sys.exit(1)

    for source_dashboard_search in r_source_dashboard_search.json():
      logger.info(f'{source_dashboard_search["uid"]} Processing dashboard {source_dashboard_search["title"]}')

      try:
        r_source_dashboard_fetch = requests.get(args.grafana_source_url + '/api/dashboards/uid/' + source_dashboard_search['uid'], headers=grafana_source_headers)
        r_source_dashboard_fetch.raise_for_status()
      except requests.RequestException as err:
        logger.error(f'{source_dashboard_search["uid"]} Could not fetch dashboard from grafana source: {err}')
        sys.exit(1)

      dashboard_data = r_source_dashboard_fetch.json()

      if dashboard_data['dashboard']['uid'] in source_dashboards:
        if source_dashboards[dashboard_data['dashboard']['uid']]['version'] == dashboard_data['dashboard']['version']:
          logger.debug(f'Already processed dashboard {dashboard_data["dashboard"]["uid"]}. Version is still {dashboard_data["dashboard"]["version"]}. Not updating.')
          continue
        else:
          logger.debug(f'Already processed dashboard {dashboard_data["dashboard"]["uid"]} but version has changed from {source_dashboards[dashboard_data["dashboard"]["uid"]]["version"]} to {dashboard_data["dashboard"]["version"]}. Marking for update.')
          source_dashboards[dashboard_data['dashboard']['uid']]['new_version'] = True

      # print("Dashboard data: " + json.dumps(dashboard_data['dashboard']['tags'], indent=4) )

      dashboard = {
        'uid': dashboard_data['dashboard']['uid'],
        'title': dashboard_data['dashboard']['title'],
        'version': dashboard_data['dashboard']['version'],
        'new_version': True,
        'in_destination': True,
        'destination_editable': False,
        'dashboard_data': dashboard_data,
      }

      if 'folderTitle' in dashboard_data['meta']: # Dashboard is in a folder
        dashboard['folderTitle'] = dashboard_data['meta']['folderTitle']
        if dashboard_data['meta']['folderTitle'] in destinationFolderIds:
          dashboard['destinationFolderId'] = destinationFolderIds[dashboard_data['meta']['folderTitle']]
          logger.debug(f'Found dashboard {dashboard_data["dashboard"]["uid"]} / {dashboard_data["dashboard"]["title"]} in folder {dashboard_data["meta"]["folderTitle"]} which has folderId {destinationFolderIds[dashboard_data["meta"]["folderTitle"]]} in destination')
        else:
          # TODO: Add option to create folders automatically?
          logger.warn('Folder ' + dashboard_data['meta']['folderTitle'] + ' does not exist in destination. Please create it first.')
          break
      else: # Dashboard is not in a folder
        dashboard['destinationFolderId'] = destinationFolderIds["General"]
        logger.debug(f'Dashboard {dashboard.get("uid")}/{dashboard.get("title")} is without folder (General)')

      source_dashboards[dashboard_data['dashboard']['uid']] = dashboard

    # logger.debug(source_dashboards)

    for dashboard_uid in source_dashboards:

      try:
        r_destination_dashboard_fetch = requests.get(args.grafana_destination_url + '/api/dashboards/uid/' + dashboard_uid, headers=grafana_destination_headers)
        if r_destination_dashboard_fetch.status_code != 200 and r_destination_dashboard_fetch.status_code != 404:
          r_destination_dashboard_fetch.raise_for_status()
      except requests.RequestException as err:
        logger.error(f'{dashboard_uid} Could not fetch dashboard from grafana destination: {err}')
        sys.exit(1)

      if r_destination_dashboard_fetch.status_code == 404:
        source_dashboards[dashboard_uid]['in_destination'] = False
        logger.debug(f'Dashboard {dashboard_uid} not found in destination.')
      else:
        if r_destination_dashboard_fetch.json()['dashboard']['editable']:
          source_dashboards[dashboard_uid]['destination_editable'] = True
          logger.debug(f'Dashboard {dashboard_uid} is editable in destination.')

    for dashboard_uid in source_dashboards:

      dashboard = source_dashboards[dashboard_uid]

      logger.debug(f'Dashboard {dashboard_uid} New version: {dashboard["new_version"]} Destination editable: {dashboard["destination_editable"]} Exists in destination: {dashboard["in_destination"]}')
      if not dashboard['new_version'] and not dashboard['destination_editable'] and dashboard['in_destination']:
        logger.debug(f'Dashboard {dashboard_uid} does not have new version. Dashboard exists in destination but is not editable. Skipping update.')
        continue

      logger.debug(f'Copying dashboard {dashboard["title"]}/{dashboard_uid} to folder {dashboard["destinationFolderId"]}')

      if 'meta' in dashboard['dashboard_data']:
        del dashboard['dashboard_data']['meta']
      if 'id' in dashboard['dashboard_data']['dashboard']:
        del dashboard['dashboard_data']['dashboard']['id']

      dashboard['dashboard_data']['dashboard']['editable'] = False

      dashboard['dashboard_data']['folderId'] = dashboard['destinationFolderId']
      dashboard['dashboard_data']['message'] = 'Dashboard cloned'
      dashboard['dashboard_data']['overwrite'] = True

      dashboard['dashboard_data']['dashboard']['tags'].remove(args.dashboard_source_clone_tag)
      dashboard['dashboard_data']['dashboard']['tags'].append(args.dashboard_destination_clone_tag)

      if args.dry_run:
        logger.info(f'Dry run: not saving dashboard {dashboard["title"]}/{dashboard_uid} to {args.grafana_destination_url}/api/dashboards/db')
      else:
        try:
          r = requests.post(args.grafana_destination_url + '/api/dashboards/db', json=dashboard['dashboard_data'], headers=grafana_destination_headers)
          r.raise_for_status()
        except requests.RequestException as err:
          logger.error(f'Could not save dashboard {destinationFolderIds[source_dashboards[dashboard_uid]]}/{dashboard} to grafana destination: {err}')
          sys.exit(1)

      source_dashboards[dashboard_uid]['new_version'] = False

    if args.daemon:
      logger.info(f'Running in daemon mode. Sleeping for {args.daemon_sync_interval_sec} seconds')
      time.sleep(args.daemon_sync_interval_sec)
    else:
      break

def environ_or_required(key):
    return (
        {'default': os.environ.get(key)} if os.environ.get(key)
        else {'required': True}
    )

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Clone dashboards from one Grafana instance to another.')
  parser.add_argument('--grafana-source-url', **environ_or_required('GRAFANA_SOURCE_URL'), help='URL for grafana instance to clone dashboards from')
  parser.add_argument('--grafana-source-apikey', **environ_or_required('GRAFANA_SOURCE_APIKEY'), help='API Key for grafana instance to clone dashboards from')
  parser.add_argument('--grafana-destination-url', **environ_or_required('GRAFANA_DESTINATION_URL'), help='URL for grafana instance to clone dashboards to')
  parser.add_argument('--grafana-destination-apikey', **environ_or_required('GRAFANA_DESTINATION_APIKEY'), help='API Key for grafana instance to clone dashboards to')
  parser.add_argument('--dashboard-source-clone-tag', **environ_or_required('DASHBOARD_SOURCE_CLONE_TAG'), help='Dashboards with this tag will be cloned.')
  parser.add_argument('--dashboard-destination-clone-tag', **environ_or_required('DASHBOARD_DESTINATION_CLONE_TAG'), help='Cloned dashboards will get this tag added.')

  parser.add_argument('--dry-run', help='Dry run. Only output what would be done without saving dashboards in destination.')
  parser.add_argument('--log-level', default="info", help='Log level. debug, info, warning, error, critical')
  parser.add_argument('--log-format', default="text", help='Log format. "json" or "text"')

  parser.add_argument('--daemon', default=False, help='Run perpetually in loop.')
  parser.add_argument('--daemon-sync-interval-sec', type=int, default=300, help='Sync interval in daemon mode.')

  args = parser.parse_args()

  log_level = getattr(logging, args.log_level.upper(), None)
  logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s')

  logger = logging.getLogger('grafanadashboardcloner')
  logger.setLevel(level=log_level)

  if args.log_format == "json":
    json_logging.init_non_web(enable_json=True)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.propagate = False

  main()

