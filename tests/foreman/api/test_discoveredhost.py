"""API Tests for foreman discovery feature

:Requirement: DiscoveredHost

:CaseComponent: DiscoveryImage

:Team: Rocket

:CaseAutomation: Automated

"""

import re

from fauxfactory import gen_choice, gen_ipaddr, gen_mac, gen_string
from nailgun import entity_mixins
import pytest
from wait_for import TimedOutError, wait_for

from robottelo.logging import logger
from robottelo.utils.datafactory import valid_data_list


class HostNotDiscoveredException(Exception):
    """Raised when host is not discovered"""


def _read_log(ch, pattern):
    """Read the first line from the given channel buffer and return the matching line"""
    # read lines until the buffer is empty
    for log_line in ch.result.stdout.splitlines():
        logger.debug(f'foreman-tail: {log_line}')
        if re.search(pattern, log_line):
            return log_line
    else:
        return None


def _wait_for_log(channel, pattern, timeout=5, delay=0.2):
    """_read_log method enclosed in wait_for method"""
    matching_log = wait_for(
        _read_log,
        func_args=(
            channel,
            pattern,
        ),
        fail_condition=None,
        timeout=timeout,
        delay=delay,
        logger=logger,
    )
    return matching_log.out


def _assert_discovered_host(host, channel=None, user_config=None):
    """Check if host is discovered and information about it can be
    retrieved back
    Introduced a delay of 300secs by polling every 10 secs to get expected
    host
    """
    # assert that server receives DHCP discover from hosts PXELinux
    for pattern in [
        (
            f"DHCPDISCOVER from {host.mac}",
            "DHCPDISCOVER",
        ),
        (f"DHCPACK on [0-9.]+ to {host.mac}", "DHCPACK"),
    ]:
        try:
            dhcp_pxe = _wait_for_log(channel, pattern[0], timeout=10)
        except TimedOutError as err:
            # raise assertion error
            raise AssertionError(f'Timed out waiting for {pattern[1]} from VM') from err
    groups = re.search('DHCPACK on (\\d.+) to', dhcp_pxe.out)
    assert len(groups.groups()) == 1, 'Unable to parse bootloader ip address'
    pxe_ip = groups.groups()[0]
    # assert that server retrieves pxelinux config over TFTP
    for pattern in [
        (f'Client {pxe_ip} finished pxelinux.0', 'pxelinux.0'),
        (f'Client {pxe_ip} finished pxelinux.cfg/default', 'pxelinux.cfg/default'),
        (f'Client {pxe_ip} finished boot/fdi-image/vmlinuz0', 'fdi-image/vmlinuz0'),
        (f'Client {pxe_ip} finished boot/fdi-image/initrd0.img', 'fdi-image/initrd0.img'),
    ]:
        try:
            _wait_for_log(channel, pattern[0], timeout=20)
        except TimedOutError as err:
            # raise assertion error
            raise AssertionError(f'Timed out waiting for VM (tftp) to fetch {pattern[1]}') from err
    # assert that server receives DHCP discover from FDI
    for pattern in [
        (
            f"DHCPDISCOVER from {host.mac}",
            "DHCPDISCOVER",
        ),
        (f"DHCPACK on [0-9.]+ to {host.mac}", "DHCPACK"),
    ]:
        try:
            dhcp_fdi = _wait_for_log(channel, pattern[0], timeout=30)
        except TimedOutError as err:
            # raise assertion error
            raise AssertionError(f'Timed out waiting for {pattern[1]} from VM') from err
    groups = re.search('DHCPACK on (\\d.+) to', dhcp_fdi.out)
    assert len(groups.groups()) == 1, 'Unable to parse FDI ip address'
    fdi_ip = groups.groups()[0]
    # finally, assert that the FDI successfully uploaded its facts to the server
    try:
        facts_fdi = _wait_for_log(
            channel,
            f'\\[I\\|app\\|[a-z0-9]+\\] Started POST "/api/v2/discovered_hosts/facts" for {fdi_ip}',
            timeout=60,
        )
    except TimedOutError as err:
        # raise assertion error
        raise AssertionError('Timed out waiting for /facts POST request') from err
    groups = re.search('\\[I\\|app\\|([a-z0-9]+)\\]', facts_fdi.out)
    assert len(groups.groups()) == 1, 'Unable to parse POST request UUID'
    req_id = groups.groups()[0]
    try:
        _wait_for_log(channel, f'\\[I\\|app\\|{req_id}\\] Completed 201 Created')
    except TimedOutError as err:
        # raise assertion error
        raise AssertionError('Timed out waiting for "/facts" 201 response') from err
    default_config = entity_mixins.DEFAULT_SERVER_CONFIG
    try:
        wait_for(
            lambda: len(
                host.api.DiscoveredHost(user_config or default_config).search(
                    query={'search': f'name={host.guest_name}'}
                )
            )
            > 0,
            timeout=20,
            delay=2,
            logger=logger,
        )
    except TimedOutError as err:
        raise AssertionError(
            'Timed out waiting for discovered_host to appear on satellite'
        ) from err
    discovered_host = host.api.DiscoveredHost(user_config or default_config).search(
        query={'search': f'name={host.guest_name}'}
    )
    return discovered_host[0]


def assert_discovered_host_provisioned(channel, ksrepo):
    """Reads foreman logs until host provisioning messages are found"""
    endpoint = '/'.join(ksrepo.full_path.split('/')[3:-1])
    pattern = f'GET /{endpoint}'
    try:
        log = _wait_for_log(channel, pattern, timeout=300, delay=10)
        assert pattern in log
    except TimedOutError as err:
        raise AssertionError(f'Timed out waiting for {pattern} from VM') from err


@pytest.fixture
def discovered_host_cleanup(target_sat):
    hosts = target_sat.api.DiscoveredHost().search()
    for host in hosts:
        host.delete()


class TestDiscoveredHost:
    """General Discovered Host tests."""

    @pytest.mark.upgrade
    @pytest.mark.e2e
    @pytest.mark.on_premises_provisioning
    @pytest.mark.parametrize('module_provisioning_sat', ['discovery'], indirect=True)
    @pytest.mark.parametrize('pxe_loader', ['bios', 'uefi'], indirect=True)
    @pytest.mark.rhel_ver_list([8, 9])
    def test_positive_provision_pxe_host(
        self,
        module_provisioning_rhel_content,
        module_discovery_sat,
        provisioning_host,
        provisioning_hostgroup,
        pxe_loader,
        request,
    ):
        """Provision a pxe-based discovered host

        :id: e805b9c5-e8f6-4129-a0e6-ab54e5671ddb

        :parametrized: yes

        :Setup: Provisioning and discovery should be configured

        :steps:
            1. Boot up the host to discover
            2. Provision the host

        :expectedresults: Host should be provisioned successfully

        :CaseImportance: Critical
        """
        sat = module_discovery_sat.sat
        provisioning_host.power_control(ensure=False)
        mac = provisioning_host.provisioning_nic_mac_addr
        wait_for(
            lambda: sat.api.DiscoveredHost().search(query={'mac': mac}) != [],
            timeout=1500,
            delay=40,
        )
        discovered_host = sat.api.DiscoveredHost().search(query={'mac': mac})[0]
        discovered_host.hostgroup = provisioning_hostgroup
        discovered_host.location = provisioning_hostgroup.location[0]
        discovered_host.organization = provisioning_hostgroup.organization[0]
        discovered_host.build = True
        with sat.session.shell() as shell:
            shell.send('foreman-tail')
            host = discovered_host.update(['hostgroup', 'build', 'location', 'organization'])
            host = sat.api.Host().search(query={"search": f'name={host.name}'})[0]
            assert host
            shell.close()
        assert_discovered_host_provisioned(shell, module_provisioning_rhel_content.ksrepo)
        request.addfinalizer(lambda: sat.provisioning_cleanup(host.name))

    @pytest.mark.upgrade
    @pytest.mark.e2e
    @pytest.mark.on_premises_provisioning
    @pytest.mark.parametrize('module_provisioning_sat', ['discovery'], indirect=True)
    @pytest.mark.parametrize('pxe_loader', ['bios', 'uefi'], indirect=True)
    @pytest.mark.rhel_ver_list([8, 9])
    def test_positive_provision_pxe_less_host(
        self,
        module_discovery_sat,
        pxeless_discovery_host,
        module_provisioning_rhel_content,
        provisioning_hostgroup,
        request,
    ):
        """Provision a pxe-less discovered hosts

        :id: 91bb254b-3c30-4608-b1ba-e18bcc22efb5

        :Setup: Provisioning should be configured and a host should be
            discovered

        :steps: PUT /api/v2/discovered_hosts/:id

        :expectedresults: Host should be provisioned successfully

        :CaseImportance: Critical
        """
        sat = module_discovery_sat.sat
        pxeless_discovery_host.power_control(ensure=False)
        mac = pxeless_discovery_host.provisioning_nic_mac_addr
        wait_for(
            lambda: sat.api.DiscoveredHost().search(query={'mac': mac}) != [],
            timeout=1500,
            delay=40,
        )
        discovered_host = sat.api.DiscoveredHost().search(query={'mac': mac})[0]
        discovered_host.hostgroup = provisioning_hostgroup
        discovered_host.location = provisioning_hostgroup.location[0]
        discovered_host.organization = provisioning_hostgroup.organization[0]
        discovered_host.build = True
        with sat.session.shell() as shell:
            shell.send('foreman-tail')
            host = discovered_host.update(['hostgroup', 'build', 'location', 'organization'])
            host = sat.api.Host().search(query={"search": f'name={host.name}'})[0]
            assert host
            shell.close()
        assert_discovered_host_provisioned(shell, module_provisioning_rhel_content.ksrepo)
        request.addfinalizer(lambda: sat.provisioning_cleanup(host.name))

    def test_positive_auto_provision_pxe_host(
        self, module_discovery_hostgroup, module_target_sat, discovery_org, discovery_location
    ):
        """Auto provision a pxe-based host by executing discovery rules

        :id: c93fd7c9-41ef-4eb5-8042-f72e87e67e10

        :parametrized: yes

        :Setup: Provisioning should be configured and a host should be
            discovered

        :steps: POST /api/v2/discovered_hosts/:id/auto_provision

        :expectedresults: Selected Host should be auto-provisioned successfully

        :CaseImportance: Critical
        """
        discovered_host = module_target_sat.api_factory.create_discovered_host()

        rule = module_target_sat.api.DiscoveryRule(
            max_count=1,
            hostgroup=module_discovery_hostgroup,
            search_=f'name = {discovered_host["name"]}',
            location=[discovery_location],
            organization=[discovery_org],
        ).create()
        result = module_target_sat.api.DiscoveredHost(id=discovered_host['id']).auto_provision()
        assert f'provisioned with rule {rule.name}' in result['message']

    def test_positive_auto_provision_all(
        self, module_discovery_hostgroup, module_target_sat, discovery_org, discovery_location
    ):
        """Auto provision all host by executing discovery rules

        :id: 954d3688-62d9-47f7-9106-a4fff8825ffa

        :Setup: Provisioning should be configured and more than one host should
            be discovered

        :steps: POST /api/v2/discovered_hosts/auto_provision_all

        :expectedresults: All discovered hosts should be auto-provisioned
            successfully

        :CaseAutomation: Automated

        :CaseImportance: High
        """
        module_target_sat.api.DiscoveryRule(
            max_count=25,
            hostgroup=module_discovery_hostgroup,
            search_=f'location = "{discovery_location.name}"',
            location=[discovery_location],
            organization=[discovery_org],
        ).create()

        for _ in range(2):
            module_target_sat.api_factory.create_discovered_host()

        result = module_target_sat.api.DiscoveredHost().auto_provision_all()
        assert '2 discovered hosts were provisioned' in result['message']

    @pytest.mark.stubbed
    def test_positive_refresh_facts_pxe_host(self, module_target_sat):
        """Refresh the facts of pxe based discovered hosts by adding a new NIC

        :id: 413fb608-cd5c-441d-af86-fd2d40346d96

        :Setup:
            1. Provisioning should be configured and more than one host should
            be discovered
            2. Add a NIC on discovered host

        :steps: PUT /api/v2/discovered_hosts/:id/refresh_facts

        :expectedresults: Added Fact should be displayed on refreshing the
            facts

        :CaseImportance: High
        """

    @pytest.mark.on_premises_provisioning
    @pytest.mark.parametrize('module_provisioning_sat', ['discovery'], indirect=True)
    @pytest.mark.parametrize('pxe_loader', ['uefi'], indirect=True)
    @pytest.mark.rhel_ver_match('9')
    def test_positive_reboot_pxe_host(
        self,
        module_provisioning_rhel_content,
        module_discovery_sat,
        provisioning_host,
        provisioning_hostgroup,
        pxe_loader,
    ):
        """Rebooting a pxe based discovered host

        :id: 69c807f8-5646-4aa6-8b3c-5ecab69560fc

        :parametrized: yes

        :Setup: Provisioning should be configured and a host should be discovered via PXE boot.

        :steps: PUT /api/v2/discovered_hosts/:id/reboot

        :expectedresults: Selected host should be rebooted successfully

        :CaseImportance: Medium
        """
        sat = module_discovery_sat.sat
        provisioning_host.power_control(ensure=False)
        mac = provisioning_host.provisioning_nic_mac_addr
        wait_for(
            lambda: sat.api.DiscoveredHost().search(query={'mac': mac}) != [],
            timeout=1500,
            delay=20,
        )

        discovered_host = sat.api.DiscoveredHost().search(query={'mac': mac})[0]
        discovered_host.hostgroup = provisioning_hostgroup
        discovered_host.location = provisioning_hostgroup.location[0]
        discovered_host.organization = provisioning_hostgroup.organization[0]
        discovered_host.build = True
        result = sat.api.DiscoveredHost(id=discovered_host.id).reboot()
        assert 'Unable to perform reboot' not in result

    @pytest.mark.on_premises_provisioning
    @pytest.mark.parametrize('module_provisioning_sat', ['discovery'], indirect=True)
    @pytest.mark.rhel_ver_match('9')
    def test_positive_reboot_all_pxe_hosts(
        self,
        module_provisioning_rhel_content,
        module_discovery_sat,
        provisioning_host,
        provisioning_hostgroup,
        pxe_loader,
    ):
        """Rebooting all pxe-based discovered hosts

        :id: 69c807f8-5646-4aa6-8b3c-5ecdb69560ed

        :parametrized: yes

        :Setup: Provisioning should be configured and hosts should be discovered via PXE boot.

        :steps: PUT /api/v2/discovered_hosts/reboot_all

        :expectedresults: All discovered hosst should be rebooted successfully

        :BlockedBy: SAT-30395

        :Verifies: SAT-23279

        :CaseImportance: Medium
        """
        sat = module_discovery_sat.sat
        provisioning_host.power_control(ensure=False)
        mac = provisioning_host.provisioning_nic_mac_addr
        wait_for(
            lambda: sat.api.DiscoveredHost().search(query={'mac': mac}) != [],
            timeout=1500,
            delay=20,
        )

        discovered_host = sat.api.DiscoveredHost().search(query={'mac': mac})[0]
        discovered_host.hostgroup = provisioning_hostgroup
        discovered_host.location = provisioning_hostgroup.location[0]
        discovered_host.organization = provisioning_hostgroup.organization[0]
        discovered_host.build = True
        result = sat.api.DiscoveredHost(id=discovered_host.id).reboot_all()
        assert 'Unable to perform reboot' not in result


class TestFakeDiscoveryTests:
    """Tests that use fake discovered host.

    :CaseImportance: High
    """

    def _create_discovered_host(self, sat, name=None, ipaddress=None, macaddress=None):
        """Creates discovered host by uploading few fake facts.

        :param str name: Name of discovered host. If ``None`` then a random
            value will be generated.
        :param str ipaddress: A valid ip address.
            If ``None`` then then a random value will be generated.
        :param str macaddress: A valid mac address.
            If ``None`` then then a random value will be generated.
        :return: A ``dict`` of ``DiscoveredHost`` facts.
        """
        if name is None:
            name = gen_string('alpha')
        if ipaddress is None:
            ipaddress = gen_ipaddr()
        if macaddress is None:
            macaddress = gen_mac(multicast=False)
        return sat.api.DiscoveredHost().facts(
            json={
                'facts': {
                    'name': name,
                    'discovery_bootip': ipaddress,
                    'discovery_bootif': macaddress,
                    'interfaces': 'eth0',
                    'ipaddress': ipaddress,
                    'macaddress': macaddress,
                    'macaddress_eth0': macaddress,
                    'ipaddress_eth0': ipaddress,
                }
            }
        )

    def test_positive_upload_facts(self, target_sat):
        """Upload fake facts to create a discovered host

        :id: c1f40204-bbb0-46d0-9b60-e42f00ad1649

        :BZ: 1349364, 1392919

        :steps:

            1. POST /api/v2/discovered_hosts/facts
            2. Read the created discovered host

        :expectedresults: Host should be created successfully

        :BZ: 1731112
        """
        name = gen_choice(list(valid_data_list().values()))
        result = self._create_discovered_host(target_sat, name)
        discovered_host = target_sat.api.DiscoveredHost(id=result['id']).read_json()
        host_name = 'mac{}'.format(discovered_host['mac'].replace(':', ''))
        assert discovered_host['name'] == host_name

    def test_positive_delete_pxe_host(self, target_sat):
        """Delete a pxe-based discovered hosts

        :id: 2ab2ad88-4470-4d4c-8e0b-5892ad8d675e

        :Setup: Provisioning should be configured and a host should be
            discovered

        :steps: DELETE /api/v2/discovered_hosts/:id

        :expectedresults: Discovered Host should be deleted successfully
        """
        name = gen_choice(list(valid_data_list().values()))
        result = self._create_discovered_host(target_sat, name)

        target_sat.api.DiscoveredHost(id=result['id']).delete()
        search = target_sat.api.DiscoveredHost().search(
            query={'search': 'name == {}'.format(result['name'])}
        )
        assert len(search) == 0
