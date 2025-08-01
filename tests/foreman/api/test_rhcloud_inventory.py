"""API tests for RH Cloud - Inventory, also known as Insights Inventory Upload

:Requirement: RHCloud

:CaseAutomation: Automated

:CaseComponent: RHCloud

:Team: Phoenix-subscriptions

:CaseImportance: High

"""

from fauxfactory import gen_alphanumeric, gen_string
import pytest

from robottelo.config import robottelo_tmp_dir
from robottelo.utils.io import get_local_file_data, get_report_data, get_report_metadata


def common_assertion(report_path):
    """Function to perform common assertions"""
    local_file_data = get_local_file_data(report_path)

    assert local_file_data['size'] > 0
    assert local_file_data['extractable']
    assert local_file_data['json_files_parsable']

    slices_in_metadata = set(local_file_data['metadata_counts'].keys())
    slices_in_tar = set(local_file_data['slices_counts'].keys())
    assert slices_in_metadata == slices_in_tar
    for slice_name, hosts_count in local_file_data['metadata_counts'].items():
        assert hosts_count == local_file_data['slices_counts'][slice_name]


@pytest.mark.run_in_one_thread
@pytest.mark.e2e
def test_rhcloud_inventory_api_e2e(
    inventory_settings,
    rhcloud_manifest_org,
    rhcloud_registered_hosts,
    module_target_sat,
):
    """Generate report using rh_cloud plugin api's and verify its basic properties.

    :id: 8ead1ff6-a8f5-461b-9dd3-f50d96d6ed57

    :expectedresults:

        1. Report can be generated
        2. Report can be downloaded
        3. Report has non-zero size
        4. Report can be extracted
        5. JSON files inside report can be parsed
        6. metadata.json lists all and only slice JSON files in tar
        7. Host counts in metadata matches host counts in slices
        8. metadata contains source and foreman_rh_cloud_version keys.
        9. Assert Hostnames, IP addresses, infrastructure type, and installed packages
            are present in report.
        10. Assert that system_purpose_sla field is present in the inventory report.

    :CaseImportance: Critical

    :BZ: 1807829, 1926100, 1965234, 1824183, 1879453, 1845113

    :customerscenario: true
    """
    org = rhcloud_manifest_org
    virtual_host, baremetal_host = rhcloud_registered_hosts
    local_report_path = robottelo_tmp_dir.joinpath(f'{gen_alphanumeric()}_{org.id}.tar.xz')
    # Generate report
    module_target_sat.generate_inventory_report(org)
    # Download report
    module_target_sat.api.Organization(id=org.id).rh_cloud_download_report(
        destination=local_report_path
    )
    common_assertion(local_report_path)
    json_data = get_report_data(local_report_path)
    json_meta_data = get_report_metadata(local_report_path)
    # Verify that metadata contains source and foreman_rh_cloud_version keys.
    prefix = 'tfm-' if module_target_sat.os_version.major < 8 else ''
    package_version = module_target_sat.run(
        f'rpm -qa --qf "%{{VERSION}}" {prefix}rubygem-foreman_rh_cloud'
    ).stdout.strip()
    assert json_meta_data['source_metadata']['foreman_rh_cloud_version'] == str(package_version)
    assert json_meta_data['source'] == 'Satellite'
    # Verify Hostnames are present in report.
    hostnames = [host['fqdn'] for host in json_data['hosts']]
    assert virtual_host.hostname in hostnames
    assert baremetal_host.hostname in hostnames
    # Verify IP addresses are present in report.
    ip_addresses = [
        host['system_profile']['network_interfaces'][0]['ipv4_addresses'][0]
        for host in json_data['hosts']
    ]
    ipv4_addresses = [host['ip_addresses'][0] for host in json_data['hosts']]
    assert virtual_host.ip_addr in ip_addresses
    assert baremetal_host.ip_addr in ip_addresses
    assert virtual_host.ip_addr in ipv4_addresses
    assert baremetal_host.ip_addr in ipv4_addresses
    # Verify infrastructure type.
    infrastructure_type = [
        host['system_profile']['infrastructure_type'] for host in json_data['hosts']
    ]
    assert 'physical' in infrastructure_type
    assert 'virtual' in infrastructure_type
    # Verify installed packages are present in report.
    all_host_profiles = [host['system_profile'] for host in json_data['hosts']]
    for host_profiles in all_host_profiles:
        assert 'installed_packages' in host_profiles
        assert len(host_profiles['installed_packages']) > 1
    # Verify that system_purpose_sla field is present in the inventory report.
    for host in json_data['hosts']:
        assert host['facts'][0]['facts']['system_purpose_role'] == 'test-role'
        assert host['facts'][0]['facts']['system_purpose_sla'] == 'Self-Support'
        assert host['facts'][0]['facts']['system_purpose_usage'] == 'test-usage'


@pytest.mark.e2e
def test_rhcloud_inventory_api_hosts_synchronization(
    rhcloud_manifest_org,
    rhcloud_registered_hosts,
    module_target_sat,
):
    """Test RH Cloud plugin api to synchronize list of available hosts from cloud.

    :id: 7be22e1c-906b-4ae5-93dd-5f79f395601c

    :steps:

        1. Prepare machine and upload its data to Insights.
        2. Sync inventory status using RH Cloud plugin api.
        3. Assert content of finished tasks.
        4. Get host details.
        5. Assert inventory status for the host.

    :expectedresults:
        1. Task detail should contain number of hosts
            synchronized and disconnected.

    :BZ: 1970223

    :CaseAutomation: Automated
    """
    org = rhcloud_manifest_org
    virtual_host, baremetal_host = rhcloud_registered_hosts
    # Generate report
    module_target_sat.generate_inventory_report(org)
    # Sync inventory status
    inventory_sync = module_target_sat.sync_inventory_status(org)
    task_output = module_target_sat.api.ForemanTask().search(
        query={'search': f'id = {inventory_sync["task"]["id"]}'}
    )
    assert task_output[0].output['host_statuses']['sync'] == 2
    assert task_output[0].output['host_statuses']['disconnect'] == 0
    # To Do: Add support in Nailgun to get Insights and Inventory host properties.


@pytest.mark.stubbed
def test_rhcloud_inventory_auto_upload_setting():
    """Verify that Automatic inventory upload setting works as expected.

    :id: 0475aaaf-c228-45af-b80c-21d459f62ecb

    :customerscenario: true

    :steps:
        1. Register a content host with satellite.
        2. Enable "Automatic inventory upload" setting.
        3. Verify that satellite automatically generate and upload
            inventory report once a day.
        4. Disable "Automatic inventory upload" setting.
        5. Verify that satellite is not automatically generating and uploading
            inventory report.

    :expectedresults:
        1. If "Automatic inventory upload" setting is enabled then satellite
        automatically generate and upload inventory report.
        2. If "Automatic inventory upload" setting is disable then satellite
        does not generate and upload inventory report automatically.

    :BZ: 1793017, 1865879

    :CaseAutomation: ManualOnly
    """


@pytest.mark.stubbed
def test_inventory_upload_with_http_proxy():
    """Verify that inventory report generate and upload process finish
    successfully when satellite is using http proxy listening on port 80.

    :id: 310a0c91-e313-474d-a5c6-64e85cea4e12

    :customerscenario: true

    :steps:
        1. Create a http proxy which is using port 80.
        2. Update general and content proxy in Satellite settings.
        3. Register a content host with satellite.
        4. Generate and upload inventory report.
        5. Assert that host is listed in the inventory report.
        6. Assert that upload process finished successfully.

    :expectedresults:
        1. Inventory report generate and upload process finished successfully.
        2. Host is present in the inventory report.

    :BZ: 1936906

    :CaseAutomation: ManualOnly
    """


@pytest.mark.run_in_one_thread
@pytest.mark.e2e
def test_include_parameter_tags_setting(
    inventory_settings,
    rhcloud_manifest_org,
    rhcloud_registered_hosts,
    module_target_sat,
):
    """Verify that include_parameter_tags setting doesn't cause invalid report
    to be generated.

    :id: 3136a1e3-f844-416b-8334-75b27fd9e3a1

    :steps:
        1. Enable include_parameter_tags setting.
        2. Register a content host with satellite.
        3. Create a host parameter with long text value.
        4. Create Hostcollection with name containing double quotes.
        5. Generate inventory report with disconnected option.
        6. Assert that generated report contains valid json file.
        7. Observe the tag generated from the parameter.

    :expectedresults:
        1. Valid json report is created.
        2. satellite_parameter values are string.
        3. Parameter tag value must not be created after the
           allowed length.
        4. Tag value is escaped properly.

    :BZ: 1981869, 1967438, 2035204, 1874587, 1874619

    :customerscenario: true

    :CaseAutomation: Automated
    """
    org = rhcloud_manifest_org
    virtual_host, baremetal_host = rhcloud_registered_hosts
    # Create a host parameter with long text value.
    param_name = gen_string('alpha')
    param_value = gen_string('alpha', length=260)
    module_target_sat.api.CommonParameter(name=param_name, value=param_value).create()
    # Create Hostcollection with name containing double quotes.
    host_col_name = gen_string('alpha')
    host_name = rhcloud_registered_hosts[0].hostname
    host = module_target_sat.api.Host().search(query={'search': host_name})[0]
    host_collection = module_target_sat.api.HostCollection(
        organization=org, name=f'"{host_col_name}"', host=[host]
    ).create()
    assert len(host_collection.host) == 1
    # Generate inventory report
    local_report_path = robottelo_tmp_dir.joinpath(f'{gen_alphanumeric()}_{org.id}.tar.xz')
    # Enable include_parameter_tags setting
    module_target_sat.update_setting('include_parameter_tags', True)
    module_target_sat.generate_inventory_report(org, disconnected='true')
    # Download report
    module_target_sat.api.Organization(id=org.id).rh_cloud_download_report(
        destination=local_report_path
    )
    json_data = get_report_data(local_report_path)
    common_assertion(local_report_path)
    # Verify that parameter tag value is not be created.
    for host in json_data['hosts']:
        for tag in host['tags']:
            if tag['key'] == param_name:
                assert tag['value'] == "Original value exceeds 250 characters"
                break
    # Verify that hostcollection tag value is escaped properly.
    for host in json_data['hosts']:
        if host['fqdn'] == host_name:
            for tag in host['tags']:
                if tag['key'] == 'host_collection':
                    assert tag['value'] == f'"{host_col_name}"'
                    break


@pytest.mark.e2e
def test_rhcloud_scheduled_insights_sync(
    rhcloud_manifest_org,
    rhcloud_registered_hosts,
    module_target_sat,
):
    """Verify that triggering the InsightsScheduledSync job in Satellite succeeds with no errors

    :id: 59f66062-2865-4cca-82bb-8d0501fd40f1

    :steps:
        1. Prepare machine and upload its data to Insights
        2. Sync inventory status using RH Cloud plugin api
        3. Trigger the InsightsScheduledSync job manually
        4. Assert job succeeds

    :expectedresults:
        1. Manually triggering the InsightsScheduledSync job succeeds with no errors.

    :Verifies: SAT-22626

    :CaseAutomation: Automated

    :customerscenario: true
    """
    org = rhcloud_manifest_org
    virtual_host, baremetal_host = rhcloud_registered_hosts
    # Generate report
    module_target_sat.generate_inventory_report(org)
    # Sync inventory status
    inventory_sync = module_target_sat.sync_inventory_status(org)
    task_output = module_target_sat.api.ForemanTask().search(
        query={'search': f'id = {inventory_sync["task"]["id"]}'}
    )
    # Assert that both hosts are synced successfully
    assert task_output[0].output['host_statuses']['sync'] == 2
    result = module_target_sat.execute(
        "foreman-rake console SATELLITE_RH_CLOUD_REQUESTS_DELAY=0 <<< 'ForemanTasks.sync_task(InsightsCloud::Async::InsightsScheduledSync)'"
    )
    assert 'success' in result.stdout
    assert result.status == 0


@pytest.mark.no_containers
@pytest.mark.run_in_one_thread
@pytest.mark.rhel_ver_list('[8,9]')
def test_rhcloud_compliance_policies(
    inventory_settings,
    rhcloud_manifest_org,
    rhcloud_registered_hosts,
    module_target_sat,
):
    """Verify that the branch_id parameter was removed from insights-client requests
    and that compliance policies are working

    :id: 21cf98a4-e5fa-4191-8fc0-e98f0e7d4f24

    :steps:
        1. Prepare machine and vm's for insights
        2. install necessary packages for compliance policies
        3. Trigger 'insights-client --compliance-policies' command
        4. Assert job succeeds

    :expectedresults:
        1. Triggering the 'insights-client --compliance-policies' command succueeds with
        no parameter errors

    :Verifies: SAT-18902

    :CaseAutomation: Automated

    :customerscenario: true
    """
    virtual_host, baremetal_host = rhcloud_registered_hosts
    virtual_host.execute("dnf install -y openscap openscap-scanner scap-security-guide")
    results = virtual_host.execute('insights-client --compliance-policies')
    assert results.status == 0
