"""Test class for Content Hosts UI

:Requirement: Content Host

:CaseAutomation: Automated

:CaseComponent: Hosts-Content

:team: Phoenix-subscriptions

:CaseImportance: High

"""

from datetime import UTC, datetime, timedelta
import re
from urllib.parse import urlparse

from fauxfactory import gen_integer, gen_string
import pytest

from robottelo.config import settings
from robottelo.constants import (
    DEFAULT_SYSPURPOSE_ATTRIBUTES,
    FAKE_0_CUSTOM_PACKAGE,
    FAKE_0_CUSTOM_PACKAGE_GROUP,
    FAKE_0_CUSTOM_PACKAGE_GROUP_NAME,
    FAKE_0_CUSTOM_PACKAGE_NAME,
    FAKE_1_CUSTOM_PACKAGE,
    FAKE_1_CUSTOM_PACKAGE_NAME,
    FAKE_1_ERRATA_ID,
    FAKE_2_CUSTOM_PACKAGE,
    FAKE_2_CUSTOM_PACKAGE_NAME,
)
from robottelo.utils.virtwho import create_fake_hypervisor_content


@pytest.fixture(scope='module', autouse=True)
def host_ui_default(module_target_sat):
    settings_object = module_target_sat.api.Setting().search(
        query={'search': 'name=host_details_ui'}
    )[0]
    settings_object.value = 'No'
    settings_object.update({'value'})
    yield
    settings_object.value = 'Yes'
    settings_object.update({'value'})


@pytest.fixture(scope='module')
def module_org(module_target_sat):
    org = module_target_sat.api.Organization(simple_content_access=False).create()
    # adding remote_execution_connect_by_ip=Yes at org level
    module_target_sat.api.Parameter(
        name='remote_execution_connect_by_ip',
        value='Yes',
        organization=org.id,
    ).create()
    return org


@pytest.fixture
def vm(module_repos_collection_with_manifest, rhel7_contenthost, target_sat):
    """Virtual machine registered in satellite"""
    module_repos_collection_with_manifest.setup_virtual_machine(rhel7_contenthost)
    rhel7_contenthost.add_rex_key(target_sat)
    rhel7_contenthost.run(r'subscription-manager repos --enable \*')
    return rhel7_contenthost


@pytest.fixture
def vm_module_streams(module_repos_collection_with_manifest, rhel8_contenthost, target_sat):
    """Virtual machine registered in satellite"""
    module_repos_collection_with_manifest.setup_virtual_machine(rhel8_contenthost)
    rhel8_contenthost.add_rex_key(satellite=target_sat)
    return rhel8_contenthost


def set_ignore_facts_for_os(module_target_sat, value=False):
    """Helper to set 'ignore_facts_for_operatingsystem' setting"""
    ignore_setting = module_target_sat.api.Setting().search(
        query={'search': 'name="ignore_facts_for_operatingsystem"'}
    )[0]
    ignore_setting.value = str(value)
    ignore_setting.update({'value'})


def run_remote_command_on_content_host(command, vm_module_streams):
    result = vm_module_streams.run(command)
    assert result.status == 0
    return result


def get_supported_rhel_versions():
    """Helper to get the supported base rhel versions for contenthost.
    return: a list of integers
    """
    return [
        ver for ver in settings.supportability.content_hosts.rhel.versions if isinstance(ver, int)
    ]


def get_rhel_lifecycle_support(rhel_version):
    """Helper to get what the Lifecycle Support Status should be,
       based on provided rhel version.
    :param rhel_version: integer of the current base rhel version
    :return: string with the expected status of rhel version support
    """
    rhels = sorted(get_supported_rhel_versions(), reverse=True)
    rhel_lifecycle_status = 'Unknown'
    if rhel_version not in rhels:
        return rhel_lifecycle_status
    if rhels.index(rhel_version) <= 1:
        rhel_lifecycle_status = 'Full support'
    elif rhels.index(rhel_version) == 2:
        rhel_lifecycle_status = 'Approaching end of maintenance support'
    elif rhels.index(rhel_version) >= 3:
        rhel_lifecycle_status = 'End of maintenance support'
    return rhel_lifecycle_status


@pytest.mark.e2e
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_positive_end_to_end(
    vm,
    session,
    module_org,
    default_location,
    module_repos_collection_with_manifest,
):
    """Create all entities required for content host, set up host, register it
    as a content host, read content host details, install package and errata.

    :id: f43f2826-47c1-4069-9c9d-2410fd1b622c

    :setup: Register a rhel7 vm as a content host. Import repos
        collection and associated manifest.

    :steps:
        1. Install some outdated version for an applicable package
        2. In legacy Host UI, find the host status and rhel lifecycle status
        3. Using legacy ContentHost UI, find the chost and relevant details
        4. Install the errata, check legacy ContentHost UI and the updated package
        5. Delete the content host, then try to find it

    :expectedresults: content host details are the same as expected, package
        and errata installation are successful

    :parametrized: yes

    :CaseImportance: Critical

    :BlockedBy: SAT-25817
    """
    # Read rhel distro param, determine what rhel lifecycle status should be
    _distro = module_repos_collection_with_manifest.distro
    host_rhel_version = None
    if _distro.startswith('rhel'):
        host_rhel_version = int(_distro[4:])
    rhel_status = get_rhel_lifecycle_support(host_rhel_version if not None else 0)

    result = vm.run(f'yum -y install {FAKE_1_CUSTOM_PACKAGE}')
    assert result.status == 0

    with session:
        session.location.select(default_location.name)
        session.organization.select(module_org.name)
        # Ensure content host is searchable
        found_chost = session.contenthost.search(f'{vm.hostname}')
        assert found_chost, f'Search for contenthost by name: "{vm.hostname}", returned no results.'
        assert found_chost[0]['Name'] == vm.hostname
        chost = session.contenthost.read(
            vm.hostname, widget_names=['details', 'provisioning_details']
        )
        session.contenthost.update(vm.hostname, {'repository_sets.limit_to_lce': True})
        ch_reposet = session.contenthost.read(vm.hostname, widget_names=['repository_sets'])
        chost.update(ch_reposet)
        # Ensure all content host fields/tabs have appropriate values
        assert chost['details']['name'] == vm.hostname
        assert (
            chost['details']['content_view']
            == module_repos_collection_with_manifest.setup_content_data['content_view']['name']
        )
        lce_name = module_repos_collection_with_manifest.setup_content_data['lce']['name']
        assert chost['details']['lce'][lce_name][lce_name]
        ak_name = module_repos_collection_with_manifest.setup_content_data["activation_key"]["name"]
        assert chost['details']['registered_by'] == f'Activation Key {ak_name}'
        assert chost['provisioning_details']['name'] == vm.hostname
        assert module_repos_collection_with_manifest.custom_product['name'] in {
            repo['Product Name'] for repo in chost['repository_sets']['table']
        }
        actual_repos = {repo['Repository Name'] for repo in chost['repository_sets']['table']}
        expected_repos = {
            module_repos_collection_with_manifest.repos_data[repo_index].get(
                'repository-set',
                module_repos_collection_with_manifest.repos_info[repo_index]['name'],
            )
            for repo_index in range(len(module_repos_collection_with_manifest.repos_info))
        }
        assert actual_repos == expected_repos
        # Ensure host status and details show correct RHEL lifecycle status
        host_status = session.host.host_status(vm.hostname)
        host_rhel_lcs = session.contenthost.read(vm.hostname, widget_names=['permission_denied'])
        assert rhel_status in host_rhel_lcs['permission_denied']
        assert rhel_status in host_status
        # Update description
        new_description = gen_string('alpha')
        session.contenthost.update(vm.hostname, {'details.description': new_description})
        chost = session.contenthost.read(vm.hostname, widget_names='details')
        assert chost['details']['description'] == new_description
        # Install package
        result = session.contenthost.execute_package_action(
            vm.hostname, 'Package Install', FAKE_0_CUSTOM_PACKAGE_NAME
        )
        assert result['overview']['job_status'] == 'Success'
        # Ensure package installed
        packages = session.contenthost.search_package(vm.hostname, FAKE_0_CUSTOM_PACKAGE_NAME)
        assert packages[0]['Installed Package'] == FAKE_0_CUSTOM_PACKAGE
        # Install errata
        result = session.contenthost.install_errata(vm.hostname, FAKE_1_ERRATA_ID)
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        # Ensure errata installed
        packages = session.contenthost.search_package(vm.hostname, FAKE_2_CUSTOM_PACKAGE_NAME)
        assert packages[0]['Installed Package'] == FAKE_2_CUSTOM_PACKAGE
        # Delete content host
        session.contenthost.delete(vm.hostname)

        assert not session.contenthost.search(vm.hostname)


@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_positive_end_to_end_bulk_update(session, default_location, vm, target_sat):
    """Create VM, set up VM as host, register it as a content host,
    read content host details, install a package ( e.g. walrus-0.71) and
    use bulk action (Update All Packages) to update the package by name
    to a later version.

    :id: d460ba30-82c7-11e9-9af5-54ee754f2151

    :customerscenario: true

    :expectedresults: package installation and update to a later version
        are successful.

    :BZ: 1712069, 1838800

    :parametrized: yes
    """
    hc_name = gen_string('alpha')
    description = gen_string('alpha')
    result = vm.run(f'yum -y install {FAKE_1_CUSTOM_PACKAGE}')
    assert result.status == 0
    with session:
        session.location.select(default_location.name)
        # Ensure content host is searchable
        assert session.contenthost.search(vm.hostname)[0]['Name'] == vm.hostname
        # Update package using bulk action
        # use the Host Collection view to access Update Packages dialogue
        session.hostcollection.create(
            {
                'name': hc_name,
                'unlimited_hosts': False,
                'max_hosts': 2,
                'description': description,
            }
        )
        session.hostcollection.associate_host(hc_name, vm.hostname)
        # For BZ#1838800, assert the Host Collection Errata Install table has the search URI
        p = urlparse(session.hostcollection.search_applicable_hosts(hc_name, FAKE_1_ERRATA_ID))
        query = f'search=installable_errata%3D{FAKE_1_ERRATA_ID}'
        assert p.hostname == target_sat.hostname
        assert p.path == '/content_hosts'
        assert p.query == query
        # Note time for later wait_for_tasks, and include 4 mins margin of safety.
        timestamp = (datetime.now(UTC) - timedelta(minutes=4)).strftime('%Y-%m-%d %H:%M')
        # Update the package by name
        session.hostcollection.manage_packages(
            hc_name,
            content_type='rpm',
            packages=FAKE_1_CUSTOM_PACKAGE_NAME,
            action='update_all',
            action_via='via remote execution',
        )
        # Wait for applicability update event (in case Satellite system slow)
        target_sat.wait_for_tasks(
            search_query='label = Actions::Katello::Applicability::Hosts::BulkGenerate'
            f' and started_at >= "{timestamp}"'
            f' and state = stopped'
            f' and result = success',
            search_rate=15,
            max_tries=10,
        )
        # Ensure package updated to a later version
        packages = session.contenthost.search_package(vm.hostname, FAKE_2_CUSTOM_PACKAGE_NAME)
        assert packages[0]['Installed Package'] == FAKE_2_CUSTOM_PACKAGE
        # Delete content host
        session.contenthost.delete(vm.hostname)


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_negative_install_package(session, default_location, vm):
    """Attempt to install non-existent package to a host remotely

    :id: d60b70f9-c43f-49c0-ae9f-187ffa45ac97

    :customerscenario: true

    :BZ: 1262940

    :expectedresults: Task finished with warning

    :parametrized: yes
    """
    with session:
        session.location.select(default_location.name)
        result = session.contenthost.execute_package_action(
            vm.hostname, 'Package Install', gen_string('alphanumeric')
        )
        assert result['overview']['job_status'] == 'Failed'


@pytest.mark.skipif((not settings.robottelo.REPOS_HOSTING_URL), reason='Missing repos_hosting_url')
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_positive_remove_package(session, default_location, vm):
    """Remove a package from a host remotely

    :id: 86d8896b-06d9-4c99-937e-f3aa07b4eb69

    :expectedresults: Package was successfully removed

    :parametrized: yes
    """
    vm.download_install_rpm(settings.repos.yum_6.url, FAKE_0_CUSTOM_PACKAGE)
    with session:
        session.location.select(default_location.name)
        result = session.contenthost.execute_package_action(
            vm.hostname, 'Package Remove', FAKE_0_CUSTOM_PACKAGE_NAME
        )
        assert result['overview']['job_status'] == 'Success'
        packages = session.contenthost.search_package(vm.hostname, FAKE_0_CUSTOM_PACKAGE_NAME)
        assert not packages


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_positive_upgrade_package(session, default_location, vm):
    """Upgrade a host package remotely

    :id: 1969db93-e7af-4f5f-973d-23c222224db6

    :expectedresults: Package was successfully upgraded

    :parametrized: yes
    """
    vm.run(f'yum install -y {FAKE_1_CUSTOM_PACKAGE}')
    with session:
        session.location.select(default_location.name)
        result = session.contenthost.execute_package_action(
            vm.hostname, 'Package Update', FAKE_1_CUSTOM_PACKAGE_NAME
        )
        assert result['overview']['job_status'] == 'Success'
        packages = session.contenthost.search_package(vm.hostname, FAKE_2_CUSTOM_PACKAGE)
        assert packages[0]['Installed Package'] == FAKE_2_CUSTOM_PACKAGE


@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_positive_install_package_group(session, default_location, vm):
    """Install a package group to a host remotely

    :id: a43fb21b-5f6a-4f14-8cd6-114ec287540c

    :expectedresults: Package group was successfully installed

    :parametrized: yes
    """
    with session:
        session.location.select(default_location.name)
        result = session.contenthost.execute_package_action(
            vm.hostname,
            'Group Install (Deprecated)',
            FAKE_0_CUSTOM_PACKAGE_GROUP_NAME,
        )
        assert result['overview']['job_status'] == 'Success'
        for package in FAKE_0_CUSTOM_PACKAGE_GROUP:
            packages = session.contenthost.search_package(vm.hostname, package)
            assert packages[0]['Installed Package'] == package


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.no_containers
def test_positive_remove_package_group(session, default_location, vm):
    """Remove a package group from a host remotely

    :id: dbeea1f2-adf4-4ad8-a989-efad8ce21b98

    :expectedresults: Package group was successfully removed

    :parametrized: yes
    """
    with session:
        session.location.select(default_location.name)
        for action in ('Group Install (Deprecated)', 'Group Remove (Deprecated)'):
            result = session.contenthost.execute_package_action(
                vm.hostname, action, FAKE_0_CUSTOM_PACKAGE_GROUP_NAME
            )
            assert result['overview']['job_status'] == 'Success'
        for package in FAKE_0_CUSTOM_PACKAGE_GROUP:
            assert not session.contenthost.search_package(vm.hostname, package)


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
def test_positive_search_errata_non_admin(
    default_location, vm, test_name, default_viewer_role, module_target_sat
):
    """Search for host's errata by non-admin user with enough permissions

    :id: 5b8887d2-987f-4bce-86a1-8f65ca7e1195

    :customerscenario: true

    :BZ: 1255515, 1662405, 1652938

    :expectedresults: User can access errata page and proper errata is
        listed

    :parametrized: yes
    """
    vm.run(f'yum install -y {FAKE_1_CUSTOM_PACKAGE}')
    with module_target_sat.ui_session(
        test_name, user=default_viewer_role.login, password=default_viewer_role.password
    ) as session:
        session.location.select(default_location.name)
        chost = session.contenthost.read(vm.hostname, widget_names='errata')
        assert settings.repos.yum_6.errata[2] in {
            errata['Id'] for errata in chost['errata']['table']
        }


@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
def test_positive_ensure_errata_applicability_with_host_reregistered(session, default_location, vm):
    """Ensure that errata remain available to install when content host is
    re-registered

    :id: 30b1e512-45e5-481e-845f-5344ed81450d

    :customerscenario: true

    :steps:
        1. Prepare an activation key with content view that contain a
            repository with a package that has errata
        2. Register the host to activation key
        3. Install the package that has errata
        4. Refresh content host subscription running:
            "subscription-manager refresh  && yum repolist"
        5. Ensure errata is available for installation
        6. Refresh content host subscription running:
            "subscription-manager refresh  && yum repolist"

    :expectedresults: errata is available in installable errata list

    :BZ: 1463818

    :parametrized: yes
    """
    vm.run(f'yum install -y {FAKE_1_CUSTOM_PACKAGE}')
    result = vm.run(f'rpm -q {FAKE_1_CUSTOM_PACKAGE}')
    assert result.status == 0
    result = vm.run('subscription-manager refresh  && yum repolist')
    assert result.status == 0
    with session:
        session.location.select(default_location.name)
        chost = session.contenthost.read(vm.hostname, widget_names='errata')
        assert settings.repos.yum_6.errata[2] in {
            errata['Id'] for errata in chost['errata']['table']
        }
        result = vm.run('subscription-manager refresh  && yum repolist')
        assert result.status == 0
        chost = session.contenthost.read(vm.hostname, widget_names='errata')
        assert settings.repos.yum_6.errata[2] in {
            errata['Id'] for errata in chost['errata']['table']
        }


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
def test_positive_host_re_registration_with_host_rename(
    session, default_location, module_org, module_repos_collection_with_manifest, vm
):
    """Ensure that content host should get re-registered after change in the hostname

    :id: c11f4e69-6ef5-45ab-aff5-00cf2d87f209

    :customerscenario: true

    :steps:
        1. Prepare an activation key with content view and repository
        2. Register the host to activation key
        3. Install the package from repository
        4. Unregister the content host
        5. Change the hostname of content host
        6. Re-register the same content host again

    :expectedresults: Re-registration should work as expected even after change in hostname

    :BZ: 1762793

    :parametrized: yes
    """
    vm.run(f'yum install -y {FAKE_1_CUSTOM_PACKAGE}')
    result = vm.run(f'rpm -q {FAKE_1_CUSTOM_PACKAGE}')
    assert result.status == 0
    vm.unregister()
    updated_hostname = f'{gen_string("alpha")}.{vm.hostname}'.lower()
    vm.run(f'hostnamectl set-hostname {updated_hostname}')
    assert result.status == 0
    vm.register_contenthost(
        module_org.name,
        activation_key=module_repos_collection_with_manifest.setup_content_data['activation_key'][
            'name'
        ],
    )
    assert result.status == 0
    with session:
        session.location.select(default_location.name)
        assert session.contenthost.search(updated_hostname)[0]['Name'] == updated_hostname


@pytest.mark.run_in_one_thread
@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
def test_positive_check_ignore_facts_os_setting(
    session, default_location, vm, module_org, request, module_target_sat
):
    """Verify that 'Ignore facts for operating system' setting works
    properly

    :steps:

        1. Create a new host entry using content host self registration
           procedure
        2. Check that there is a new setting added "Ignore facts for
           operating system", and set it to true.
        3. Upload the facts that were read from initial host, but with a
           change in all the operating system fields to a different OS or
           version.
        4. Verify that the host OS isn't updated.
        5. Set the setting in step 2 to false.
        6. Upload same modified facts from step 3.
        7. Verify that the host OS is updated.
        8. Verify that new OS is created

    :id: 71bed439-105c-4e87-baae-738379d055fb

    :customerscenario: true

    :expectedresults: Host facts impact its own values properly according
        to the setting values

    :BZ: 1155704

    :parametrized: yes
    """
    major = str(gen_integer(15, 99))
    minor = str(gen_integer(1, 9))
    expected_os = f'RedHat {major}.{minor}'
    set_ignore_facts_for_os(module_target_sat, False)
    host = (
        module_target_sat.api.Host()
        .search(query={'search': f'name={vm.hostname} and organization_id={module_org.id}'})[0]
        .read()
    )
    with session:
        session.location.select(default_location.name)
        # Get host current operating system value
        os = session.contenthost.read(vm.hostname, widget_names='details')['details']['os']
        # Change necessary setting to true
        set_ignore_facts_for_os(module_target_sat, True)
        # Add cleanup function to roll back setting to default value
        request.addfinalizer(lambda: set_ignore_facts_for_os(module_target_sat, False))
        # Read all facts for corresponding host
        facts = host.get_facts(data={'per_page': 10000})['results'][vm.hostname]
        # Modify OS facts to another values and upload them to the server
        # back
        facts['operatingsystem'] = 'RedHat'
        facts['osfamily'] = 'RedHat'
        facts['operatingsystemmajrelease'] = major
        facts['operatingsystemrelease'] = f'{major}.{minor}'
        host.upload_facts(data={'name': vm.hostname, 'facts': facts})
        session.contenthost.search('')
        updated_os = session.contenthost.read(vm.hostname, widget_names='details')['details']['os']
        # Check that host OS was not changed due setting was set to true
        assert os == updated_os
        # Put it to false and re-run the process
        set_ignore_facts_for_os(module_target_sat, False)
        host.upload_facts(data={'name': vm.hostname, 'facts': facts})
        session.contenthost.search('')
        updated_os = session.contenthost.read(vm.hostname, widget_names='details')['details']['os']
        # Check that host OS was changed to new value
        assert os != updated_os
        assert updated_os == expected_os
        # Check that new OS was created
        assert session.operatingsystem.search(expected_os)[0]['Title'] == expected_os


@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_module_stream_actions_on_content_host(
    session, default_location, vm_module_streams, module_target_sat
):
    """Check remote execution for module streams actions e.g. install, remove, disable
    works on content host. Verify that correct stream module stream
    get installed/removed.

    :id: 684e467e-b41c-4b95-8450-001abe85abe0

    :expectedresults: Remote execution for module actions should succeed.

    :parametrized: yes
    """
    stream_version = '5.21'
    run_remote_command_on_content_host('dnf -y upload-profile', vm_module_streams)
    module_target_sat.api.Parameter(
        name='remote_execution_connect_by_ip',
        value='Yes',
        parameter_type='boolean',
        host=vm_module_streams.hostname,
    )
    with session:
        session.location.select(default_location.name)
        # install Module Stream
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Install',
            module_name=FAKE_2_CUSTOM_PACKAGE_NAME,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == stream_version
        assert 'Enabled' in module_stream[0]['Status']
        assert 'Installed' in module_stream[0]['Status']

        # remove Module Stream
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Remove',
            module_name=FAKE_2_CUSTOM_PACKAGE_NAME,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        assert not session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=stream_version,
        )
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Enabled',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == stream_version
        assert module_stream[0]['Status'] == 'Enabled'

        # disable Module Stream
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Disable',
            module_name=FAKE_2_CUSTOM_PACKAGE_NAME,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Disabled',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == stream_version
        assert module_stream[0]['Status'] == 'Disabled'

        # reset Module Stream
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Reset',
            module_name=FAKE_2_CUSTOM_PACKAGE_NAME,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        assert not session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Disabled',
            stream_version=stream_version,
        )
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Unknown',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == stream_version
        assert module_stream[0]['Status'] == ''


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_module_streams_customize_action(session, default_location, vm_module_streams):
    """Check remote execution for customized module action is working on content host.

    :id: b139ea1f-380b-40a5-bb57-7530a52de18c

    :expectedresults: Remote execution for module actions should be succeed.

    :parametrized: yes

    :CaseImportance: Medium
    """
    search_stream_version = '5.21'
    install_stream_version = '0.71'
    run_remote_command_on_content_host('dnf -y upload-profile', vm_module_streams)
    run_remote_command_on_content_host(
        f'dnf module reset {FAKE_2_CUSTOM_PACKAGE_NAME} -y', vm_module_streams
    )
    run_remote_command_on_content_host(
        f'dnf module reset {FAKE_2_CUSTOM_PACKAGE_NAME}', vm_module_streams
    )
    with session:
        session.location.select(default_location.name)
        # installing walrus:0.71 version
        customize_values = {
            'template_content.module_spec': (
                f'{FAKE_2_CUSTOM_PACKAGE_NAME}:{install_stream_version}'
            )
        }
        # run customize action on module streams
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Install',
            module_name=FAKE_2_CUSTOM_PACKAGE_NAME,
            stream_version=search_stream_version,
            customize=True,
            customize_values=customize_values,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=install_stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == install_stream_version


@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_install_modular_errata(session, default_location, vm_module_streams):
    """Populate, Search and Install Modular Errata generated from module streams.

    :id: 3b745562-7f97-4b58-98ec-844685f5c754

    :expectedresults: Modular Errata should get installed on content host.

    :parametrized: yes
    """
    stream_version = '0'
    module_name = 'kangaroo'
    run_remote_command_on_content_host('dnf -y upload-profile', vm_module_streams)
    with session:
        session.location.select(default_location.name)
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Install',
            module_name=module_name,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'

        # downgrade rpm package to generate errata.
        run_remote_command_on_content_host(f'dnf downgrade {module_name} -y', vm_module_streams)
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            module_name,
            status='Upgrade Available',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == module_name

        # verify the errata
        chost = session.contenthost.read(vm_module_streams.hostname, 'errata')
        assert settings.repos.module_stream_0.errata[2] in {
            errata['Id'] for errata in chost['errata']['table']
        }

        # Install errata
        result = session.contenthost.install_errata(
            vm_module_streams.hostname, settings.repos.module_stream_0.errata[2], install_via='rex'
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'

        # ensure errata installed
        assert not session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            module_name,
            status='Upgrade Available',
            stream_version=stream_version,
        )

        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            module_name,
            status='Installed',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == module_name


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_module_status_update_from_content_host_to_satellite(
    session, default_location, vm_module_streams, module_org
):
    """Verify dnf upload-profile updates the module stream status to Satellite.

    :id: d05042e3-1996-4293-bb01-a2a0cc5b3b91

    :expectedresults: module stream status should get updated in Satellite

    :parametrized: yes
    """
    module_name = 'walrus'
    stream_version = '0.71'
    profile = 'flipper'
    run_remote_command_on_content_host('dnf -y upload-profile', vm_module_streams)

    # reset walrus module streams
    run_remote_command_on_content_host(f'dnf module reset {module_name} -y', vm_module_streams)

    # install walrus module stream with flipper profile
    run_remote_command_on_content_host(
        f'dnf module install {module_name}:{stream_version}/{profile} -y',
        vm_module_streams,
    )
    with session:
        session.location.select(default_location.name)
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == stream_version
        assert module_stream[0]['Installed Profile'] == profile

        # remove walrus module stream with flipper profile
        run_remote_command_on_content_host(
            f'dnf module remove {module_name}:{stream_version}/{profile} -y',
            vm_module_streams,
        )
        assert not session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=stream_version,
        )


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_module_status_update_without_force_upload_package_profile(
    session, default_location, vm_module_streams, target_sat
):
    """Verify you do not have to run dnf upload-profile or restart rhsmcertd
    to update the module stream status to Satellite and that the web UI will also be updated.

    :id: 16675b57-71c2-4aee-950b-844aa32002d1

    :expectedresults: module stream status should get updated in Satellite

    :parametrized: yes

    :CaseImportance: Medium
    """
    module_name = 'walrus'
    stream_version = '0.71'
    profile = 'flipper'
    # reset walrus module streams
    run_remote_command_on_content_host(f'dnf module reset {module_name} -y', vm_module_streams)
    # make a note of time for later wait_for_tasks, and include 4 mins margin of safety.
    timestamp = (datetime.now(UTC) - timedelta(minutes=4)).strftime('%Y-%m-%d %H:%M')
    # install walrus module stream with flipper profile
    run_remote_command_on_content_host(
        f'dnf module install {module_name}:{stream_version}/{profile} -y',
        vm_module_streams,
    )
    # Wait for applicability update event (in case Satellite system slow)
    target_sat.wait_for_tasks(
        search_query='label = Actions::Katello::Applicability::Hosts::BulkGenerate'
        f' and started_at >= "{timestamp}"'
        f' and state = stopped'
        f' and result = success',
        search_rate=15,
        max_tries=10,
    )
    with session:
        session.location.select(default_location.name)
        # Ensure content host is searchable
        assert (
            session.contenthost.search(vm_module_streams.hostname)[0]['Name']
            == vm_module_streams.hostname
        )

        # Check web UI for the new module stream version
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == FAKE_2_CUSTOM_PACKAGE_NAME
        assert module_stream[0]['Stream'] == stream_version
        assert module_stream[0]['Installed Profile'] == profile

        # remove walrus module stream with flipper profile
        run_remote_command_on_content_host(
            f'dnf module remove {module_name}:{stream_version}/{profile} -y',
            vm_module_streams,
        )
        assert not session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            FAKE_2_CUSTOM_PACKAGE_NAME,
            status='Installed',
            stream_version=stream_version,
        )


@pytest.mark.upgrade
@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_module_stream_update_from_satellite(session, default_location, vm_module_streams):
    """Verify module stream enable, update actions works and update the module stream

    :id: 8c077d7f-744b-4655-9fa2-e64ce1566d9b

    :expectedresults: module stream should get updated.

    :parametrized: yes
    """
    module_name = 'duck'
    stream_version = '0'
    run_remote_command_on_content_host('dnf -y upload-profile', vm_module_streams)
    # reset duck module
    run_remote_command_on_content_host(f'dnf module reset {module_name} -y', vm_module_streams)
    with session:
        session.location.select(default_location.name)
        # enable duck module stream
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Enable',
            module_name=module_name,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'
        module_stream = session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            module_name,
            status='Enabled',
            stream_version=stream_version,
        )
        assert module_stream[0]['Name'] == module_name
        assert module_stream[0]['Stream'] == stream_version
        assert module_stream[0]['Status'] == 'Enabled'

        # install module stream and downgrade it to generate the errata
        run_remote_command_on_content_host(
            f'dnf module install {module_name} -y', vm_module_streams
        )
        run_remote_command_on_content_host(f'dnf downgrade {module_name} -y', vm_module_streams)

        # update duck module stream
        result = session.contenthost.execute_module_stream_action(
            vm_module_streams.hostname,
            action_type='Update',
            module_name=module_name,
            stream_version=stream_version,
        )
        assert result['overview']['hosts_table'][0]['Status'] == 'success'

        # ensure module stream get updated
        assert not session.contenthost.search_module_stream(
            vm_module_streams.hostname,
            module_name,
            status='Upgrade Available',
            stream_version=stream_version,
        )


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_syspurpose_attributes_empty(session, default_location, vm_module_streams):
    """
    Test if syspurpose attributes are displayed as empty
    on a freshly provisioned and registered host.

    :id: d8ccf04f-a4eb-4c11-8376-f70857f4ef54

    :expectedresults: Syspurpose attrs are empty, and syspurpose status is set as 'Not specified'

    :parametrized: yes

    :CaseImportance: High
    """
    with session:
        session.location.select(default_location.name)
        details = session.contenthost.read(vm_module_streams.hostname, widget_names='details')[
            'details'
        ]
        assert 'system_purpose_status' not in details
        for spname in DEFAULT_SYSPURPOSE_ATTRIBUTES:
            assert details[spname] == ''


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_set_syspurpose_attributes_cli(session, default_location, vm_module_streams):
    """
    Test that UI shows syspurpose attributes set by the syspurpose tool on a registered host.

    :id: d898a3b0-2941-4fed-a725-2b8e911bba77

    :expectedresults: Syspurpose attributes set for the content host

    :parametrized: yes

    :CaseImportance: High
    """
    with session:
        session.location.select(default_location.name)
        # Set sypurpose attributes
        for spdata in DEFAULT_SYSPURPOSE_ATTRIBUTES.values():
            run_remote_command_on_content_host(
                f'syspurpose set-{spdata[0]} "{spdata[1]}"', vm_module_streams
            )

        details = session.contenthost.read(vm_module_streams.hostname, widget_names='details')[
            'details'
        ]
        for spname, spdata in DEFAULT_SYSPURPOSE_ATTRIBUTES.items():
            assert details[spname] == spdata[1]


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel8',
            'YumRepository': [
                {'url': settings.repos.rhel8_os.baseos},
                {'url': settings.repos.rhel8_os.appstream},
                {'url': settings.repos.satutils_repo},
                {'url': settings.repos.module_stream_1.url},
            ],
        }
    ],
    indirect=True,
)
def test_unset_syspurpose_attributes_cli(session, default_location, vm_module_streams):
    """
    Test that previously set syspurpose attributes are correctly set
    as empty after using 'syspurpose unset-...' on the content host.

    :id: f83ba174-20ab-4ef2-a9e2-d913d20a0b2d

    :expectedresults: Syspurpose attributes are empty

    :parametrized: yes

    :CaseImportance: High
    """
    # Set sypurpose attributes...
    for spdata in DEFAULT_SYSPURPOSE_ATTRIBUTES.values():
        run_remote_command_on_content_host(
            f'syspurpose set-{spdata[0]} "{spdata[1]}"', vm_module_streams
        )
    for spdata in DEFAULT_SYSPURPOSE_ATTRIBUTES.values():
        # ...and unset them.
        run_remote_command_on_content_host(f'syspurpose unset-{spdata[0]}', vm_module_streams)

    with session:
        session.location.select(default_location.name)
        details = session.contenthost.read(vm_module_streams.hostname, widget_names='details')[
            'details'
        ]
        for spname in DEFAULT_SYSPURPOSE_ATTRIBUTES:
            assert details[spname] == ''


@pytest.mark.parametrize(
    'module_repos_collection_with_manifest',
    [
        {
            'distro': 'rhel7',
            'RHELAnsibleEngineRepository': {'cdn': True},
            'SatelliteToolsRepository': {},
            'YumRepository': [
                {'url': settings.repos.yum_1.url},
                {'url': settings.repos.yum_6.url},
            ],
        },
    ],
    indirect=True,
)
def test_syspurpose_bulk_action(session, default_location, vm):
    """
    Set system purpose parameters via bulk action

    :id: d084b04a-5fda-418d-ae65-a16f847c8c1d

    :bz: 1905979, 1931527

    :expectedresults: Syspurpose parameters are set and reflected on the host

    :CaseImportance: High
    """
    syspurpose_attributes = {
        'service_level': 'Standard',
        'usage_type': 'Production',
        'role': 'Red Hat Enterprise Linux Server',
    }
    with session:
        session.location.select(default_location.name)
        session.contenthost.bulk_set_syspurpose([vm.hostname], syspurpose_attributes)
        details = session.contenthost.read(vm.hostname, widget_names='details')['details']
        for key, val in syspurpose_attributes.items():
            assert details[key] == val
            result = run_remote_command_on_content_host('syspurpose show', vm)
            assert val in result.stdout


def test_pagination_multiple_hosts_multiple_pages(session, module_host_template, target_sat):
    """Create hosts to fill more than one page, sort on OS, check pagination.

    Search for hosts based on operating system and assert that more than one page
    is reported to exist and that more than one page can be accessed. Make some
    additional asserts to ensure the pagination widget is working as expected.

    To avoid requiring more than 20 fakes hosts to overcome default page setting of 20,
    this test will set a new per_page default (see new_per_page_setting).
    This test is using URL method rather than the "entries_per_page" setting to avoid
    impacting other tests that might be running.

    :id: e63e4872-5fcf-4468-ab66-63ac4f4f5dac

    :customerscenario: true

    :BZ: 1642549
    """
    new_per_page_setting = 2
    host_num = new_per_page_setting + 1
    host_name = None
    start_url = f'/content_hosts?page=1&per_page={new_per_page_setting}'
    # Create more than one page of fake hosts. Need two digits in name to ensure sort order.
    for count in range(host_num):
        host_name = f'test-{count + 1:0>2}'
        target_sat.cli_factory.make_fake_host(
            {
                'name': host_name,
                'organization-id': module_host_template.organization.id,
                'architecture-id': module_host_template.architecture.id,
                'domain-id': module_host_template.domain.id,
                'location-id': module_host_template.location.id,
                'medium-id': module_host_template.medium.id,
                'operatingsystem-id': module_host_template.operatingsystem.id,
                'partition-table-id': module_host_template.ptable.id,
            }
        )
    with session(url=start_url):
        session.location.select(module_host_template.location.name)
        # Search for all the hosts by os. This uses pagination to get more than one page.
        all_fake_hosts_found = session.contenthost.search(
            f'os = {module_host_template.operatingsystem.name}'
        )
        # Check that we can't find the highest numbered host in the first page
        match = re.search(rf'test-{host_num:0>2}', str(all_fake_hosts_found))
        assert not match, 'Highest numbered host found on first page of results.'
        # Get all the pagination values
        read_values = session.contenthost.read_all()
        # Assert total pages reported is greater than one page of hosts
        total_pages = read_values['pages']
        assert int(total_pages) > int(host_num) / int(new_per_page_setting)
        # Assert that total items reported is the number of hosts created for this test
        total_items_found = read_values['total_items']
        assert int(total_items_found) >= host_num


def test_search_for_virt_who_hypervisors(session, default_location, module_target_sat):
    """
    Search the virt_who hypervisors with hypervisor=True or hypervisor=False.

    :id: 3c759e13-d5ef-4273-8e64-2cc8ed9099af

    :expectedresults: Search with hypervisor=True and hypervisor=False gives the correct result.

    :BZ: 1653386

    :customerscenario: true

    :CaseImportance: Medium
    """
    org = module_target_sat.api.Organization().create()
    with session:
        session.organization.select(org.name)
        session.location.select(default_location.name)
        assert not session.contenthost.search('hypervisor = true')
        # create virt-who hypervisor through the fake json conf
        data = create_fake_hypervisor_content(org.label, hypervisors=1, guests=1)
        hypervisor_name = data['hypervisors'][0]['name']
        hypervisor_display_name = f'virt-who-{hypervisor_name}-{org.id}'
        # Search with hypervisor=True gives the correct result.
        assert (
            (session.contenthost.search('hypervisor = true')[0]['Name']) == hypervisor_display_name
        )
        # Search with hypervisor=false gives the correct result.
        content_hosts = [host['Name'] for host in session.contenthost.search('hypervisor = false')]
        assert hypervisor_display_name not in content_hosts


def test_content_hosts_bool_in_query(target_sat):
    """
    Test that the 'true'/'false' string is also
    interpreted as a boolean true/false as it is happening for 't'/'f' string

    :id: 1daa297d-aa16-4211-9b1b-23e63c09b0e1

    :verifies: SAT-22655
    """
    search_queries = {
        'True': [
            'params.host_registration_insights = true',
            'params.host_registration_insights = t',
        ],
        'False': [
            'params.host_registration_insights = false',
            'params.host_registration_insights = f',
        ],
    }

    with target_sat.ui_session() as session:
        for query_type, queries in search_queries.items():
            for query in queries:
                session.contenthost.search(query)
                result = session.contenthost.read_all()
                if query_type == 'True':
                    assert result['table'][0]['Name'] == target_sat.hostname
                elif query_type == 'False' and result['table']:
                    assert all(item['Name'] != target_sat.hostname for item in result['table'])
