import ipaddress
import os
import re
from tempfile import mkstemp

from box import Box
from broker import Broker
from fauxfactory import gen_string
from packaging.version import Version
import pytest

from robottelo import constants
from robottelo.config import settings
from robottelo.enums import NetworkType
from robottelo.hosts import ContentHost
from robottelo.utils.issue_handlers import is_open


@pytest.fixture(scope='module')
def module_provisioning_capsule(module_target_sat, module_location):
    """Assigns the `module_location` to Satellite's internal capsule and returns it"""
    capsule = module_target_sat.nailgun_smart_proxy
    capsule.location = [module_location]
    return capsule.update(['location'])


@pytest.fixture(scope='module')
def module_provisioning_rhel_content(
    request,
    module_provisioning_sat,
    module_sca_manifest_org,
    module_lce_library,
):
    """
    This fixture sets up kickstart repositories for a specific RHEL version
    that is specified in `request.param`.
    """
    sat = module_provisioning_sat.sat
    rhel_ver = request.param['rhel_version']
    repo_names = []
    if int(rhel_ver) <= 7:
        repo_names.append(f'rhel{rhel_ver}')
    else:
        repo_names.append(f'rhel{rhel_ver}_bos')
        repo_names.append(f'rhel{rhel_ver}_aps')
    rh_repos = []
    tasks = []
    rh_repo_id = ""
    content_view = sat.api.ContentView(organization=module_sca_manifest_org).create()

    # Custom Content for Client repo
    custom_product = sat.api.Product(
        organization=module_sca_manifest_org, name=f'rhel{rhel_ver}_{gen_string("alpha")}'
    ).create()
    client_repo = sat.api.Repository(
        organization=module_sca_manifest_org,
        product=custom_product,
        content_type='yum',
        url=settings.repos.SATCLIENT_REPO[f'rhel{rhel_ver}'],
    ).create()
    task = client_repo.sync(synchronous=False)
    tasks.append(task)
    content_view.repository = [client_repo]

    for name in repo_names:
        rh_kickstart_repo_id = sat.api_factory.enable_rhrepo_and_fetchid(
            basearch=constants.DEFAULT_ARCHITECTURE,
            org_id=module_sca_manifest_org.id,
            product=constants.REPOS['kickstart'][name]['product'],
            repo=constants.REPOS['kickstart'][name]['name'],
            reposet=constants.REPOS['kickstart'][name]['reposet'],
            releasever=constants.REPOS['kickstart'][name]['version'],
        )
        # do not sync content repos for discovery based provisioning.
        if module_provisioning_sat.provisioning_type != 'discovery':
            rh_repo_id = sat.api_factory.enable_rhrepo_and_fetchid(
                basearch=constants.DEFAULT_ARCHITECTURE,
                org_id=module_sca_manifest_org.id,
                product=constants.REPOS[name]['product'],
                repo=constants.REPOS[name]['name'],
                reposet=constants.REPOS[name]['reposet'],
                releasever=constants.REPOS[name]['releasever'],
            )

        # Sync step because repo is not synced by default
        for repo_id in [rh_kickstart_repo_id, rh_repo_id]:
            if repo_id:
                rh_repo = sat.api.Repository(id=repo_id).read()
                task = rh_repo.sync(synchronous=False)
                tasks.append(task)
                rh_repos.append(rh_repo)
                content_view.repository.append(rh_repo)
                content_view.update(['repository'])
    for task in tasks:
        sat.wait_for_tasks(
            search_query=(f'id = {task["id"]}'),
            poll_timeout=2500,
            poll_rate=5 if is_open('SAT-35513') else None,
        )
        task_status = sat.api.ForemanTask(id=task['id']).poll()
        assert task_status['result'] == 'success'
    rhel_xy = Version(
        constants.REPOS['kickstart'][f'rhel{rhel_ver}']['version']
        if rhel_ver == 7
        else constants.REPOS['kickstart'][f'rhel{rhel_ver}_bos']['version']
    )
    o_systems = sat.api.OperatingSystem().search(
        query={'search': f'family=Redhat and major={rhel_xy.major} and minor={rhel_xy.minor}'}
    )
    assert o_systems, f'Operating system RHEL {rhel_xy} was not found'
    os = o_systems[0].read()
    # return only the first kickstart repo - RHEL X KS or RHEL X BaseOS KS
    ksrepo = rh_repos[0]
    publish = content_view.publish()
    task_status = sat.wait_for_tasks(
        search_query=(f'Actions::Katello::ContentView::Publish and id = {publish["id"]}'),
        search_rate=15,
        max_tries=10,
    )
    assert task_status[0].result == 'success'
    content_view = sat.api.ContentView(
        organization=module_sca_manifest_org, name=content_view.name
    ).search()[0]
    ak = sat.api.ActivationKey(
        organization=module_sca_manifest_org,
        content_view=content_view,
        environment=module_lce_library,
    ).create()

    # Ensure client repo is enabled in the activation key
    content = ak.product_content(data={'content_access_mode_all': '1'})['results']
    client_repo_label = [repo['label'] for repo in content if repo['name'] == client_repo.name][0]
    ak.content_override(
        data={'content_overrides': [{'content_label': client_repo_label, 'value': '1'}]}
    )
    return Box(os=os, ak=ak, ksrepo=ksrepo, cv=content_view)


@pytest.fixture(scope='module')
def module_provisioning_sat(
    request,
    module_target_sat,
    module_sca_manifest_org,
    module_location,
    module_provisioning_capsule,
):
    """
    This fixture sets up the Satellite for PXE provisioning.
    It calls a workflow using broker to set up the network and to run satellite-installer.
    It uses the artifacts from the workflow to create all the necessary Satellite entities
    that are later used by the tests.
    """
    provisioning_type = getattr(request, 'param', '')
    sat = module_target_sat
    provisioning_domain_name = f"{gen_string('alpha').lower()}.foo"
    sat_ipv6 = sat.network_type == NetworkType.IPV6

    broker_data_out = Broker().execute(
        workflow=settings.provisioning.provisioning_sat_workflow,
        artifacts='last',
        target_vlan_id=settings.provisioning.vlan_id,
        target_host=sat.name,
        provisioning_dns_zone=provisioning_domain_name,
        sat_version='stream' if sat.is_stream else sat.version,
    )

    broker_data_out = Box(**broker_data_out['data_out'])
    provisioning_interface = ipaddress.ip_interface(broker_data_out.provisioning_addr_ip)
    provisioning_network = provisioning_interface.network
    # TODO: investigate DNS setup issue on Satellite,
    # we might need to set up Sat's DNS server as the primary one on the Sat host
    provisioning_upstream_dns_primary = (
        broker_data_out.provisioning_upstream_dns
        if sat_ipv6
        else broker_data_out.provisioning_upstream_dns.pop()
    )  # There should always be at least one upstream DNS
    provisioning_upstream_dns_secondary = (
        broker_data_out.provisioning_upstream_dns.pop()
        if len(broker_data_out.provisioning_upstream_dns) and not sat_ipv6
        else None
    )

    domain = sat.api.Domain(
        location=[module_location],
        organization=[module_sca_manifest_org],
        dns=None if sat_ipv6 else module_provisioning_capsule.id,
        name=provisioning_domain_name,
    ).create()

    subnet = sat.api.Subnet(
        location=[module_location],
        organization=[module_sca_manifest_org],
        network=str(provisioning_network.network_address),
        network_type='IPv6' if provisioning_network.version == 6 else 'IPv4',
        vlanid=settings.provisioning.vlan_id,
        mask=str(provisioning_network.netmask),
        gateway=broker_data_out.provisioning_gw_ip,
        from_=broker_data_out.provisioning_host_range_start,
        to=broker_data_out.provisioning_host_range_end,
        dns_primary=provisioning_upstream_dns_primary,
        dns_secondary=provisioning_upstream_dns_secondary,
        boot_mode='DHCP',
        ipam='None' if provisioning_network.version == 6 else 'DHCP',
        dhcp=None if provisioning_network.version == 6 else module_provisioning_capsule.id,
        tftp=module_provisioning_capsule.id,
        template=module_provisioning_capsule.id,
        dns=None if sat_ipv6 else module_provisioning_capsule.id,
        httpboot=module_provisioning_capsule.id,
        discovery=module_provisioning_capsule.id,
        remote_execution_proxy=[module_provisioning_capsule.id],
        domain=[domain.id],
    ).create()
    return Box(sat=sat, domain=domain, subnet=subnet, provisioning_type=provisioning_type)


@pytest.fixture(scope='module')
def module_ssh_key_file():
    _, layout = mkstemp(text=True)
    os.chmod(layout, 0o600)
    with open(layout, 'w') as ssh_key:
        ssh_key.write(settings.provisioning.host_ssh_key_priv)
    return layout


@pytest.fixture
def provisioning_host(module_ssh_key_file, pxe_loader, module_provisioning_sat):
    """Fixture to check out blank VM"""
    if (
        pxe_loader.vm_firmware == 'bios'
        and module_provisioning_sat.sat.network_type == NetworkType.IPV6
    ):
        pytest.skip('BIOS is not supported with IPv6')
    vlan_id = settings.provisioning.vlan_id
    cd_iso = (
        ""  # TODO: Make this an optional fixture parameter (update vm_firmware when adding this)
    )
    with Broker(
        workflow=settings.provisioning.provisioning_host_workflow,
        host_class=ContentHost,
        target_vlan_id=vlan_id,
        target_vm_firmware=pxe_loader.vm_firmware,
        target_pxeless_image=cd_iso,
        blank=True,
        target_memory='6GiB',
        auth=module_ssh_key_file,
    ) as prov_host:
        yield prov_host
        # Set host as non-blank to run teardown of the host
        if settings.server.network_type == NetworkType.IPV4:
            assert module_provisioning_sat.sat.execute('systemctl restart dhcpd').status == 0
        prov_host.blank = getattr(prov_host, 'blank', False)


@pytest.fixture(scope='module')
def configure_kea_dhcp6_server():
    if settings.server.network_type == NetworkType.IPV6:
        kea_host = Broker(
            workflow=settings.provisioning.provisioning_kea_workflow,
            artifacts='last',
            host_class=ContentHost,
            blank=True,
            target_vlan_id=settings.provisioning.vlan_id,
        ).execute()
        yield kea_host
        Broker(workflow='remove-vm', source_vm=kea_host.name).execute()
    else:
        yield None


@pytest.fixture
def provisioning_hostgroup(
    module_provisioning_sat,
    module_sca_manifest_org,
    module_location,
    default_architecture,
    module_provisioning_rhel_content,
    module_lce_library,
    default_partitiontable,
    module_provisioning_capsule,
    pxe_loader,
):
    sat_ipv6 = module_provisioning_sat.sat.network_type == NetworkType.IPV6
    return module_provisioning_sat.sat.api.HostGroup(
        organization=[module_sca_manifest_org],
        location=[module_location],
        architecture=default_architecture,
        domain=module_provisioning_sat.domain,
        content_source=module_provisioning_capsule.id,
        content_view=module_provisioning_rhel_content.cv,
        kickstart_repository=module_provisioning_rhel_content.ksrepo,
        lifecycle_environment=module_lce_library,
        root_pass=settings.provisioning.host_root_password,
        operatingsystem=module_provisioning_rhel_content.os,
        ptable=default_partitiontable,
        subnet=module_provisioning_sat.subnet if not sat_ipv6 else None,
        subnet6=module_provisioning_sat.subnet if sat_ipv6 else None,
        pxe_loader=pxe_loader.pxe_loader,
        group_parameters_attributes=[
            {
                'name': 'remote_execution_ssh_keys',
                'parameter_type': 'string',
                'value': settings.provisioning.host_ssh_key_pub,
            },
            # assign AK in order the hosts to be subscribed
            {
                'name': 'kt_activation_keys',
                'parameter_type': 'string',
                'value': module_provisioning_rhel_content.ak.name,
            },
        ],
    ).create()


@pytest.fixture
def pxe_loader(request):
    """Map the appropriate PXE loader to VM bootloader"""
    PXE_LOADER_MAP = {
        'bios': {'vm_firmware': 'bios', 'pxe_loader': 'PXELinux BIOS'},
        'uefi': {'vm_firmware': 'uefi', 'pxe_loader': 'Grub2 UEFI'},
        'ipxe': {'vm_firmware': 'bios', 'pxe_loader': 'iPXE Embedded'},
        'http_uefi': {'vm_firmware': 'uefi', 'pxe_loader': 'Grub2 UEFI HTTP'},
        'secureboot': {'vm_firmware': 'uefi_secure_boot', 'pxe_loader': 'Grub2 UEFI SecureBoot'},
    }
    return Box(PXE_LOADER_MAP[getattr(request, 'param', 'uefi')])


@pytest.fixture
def pxeless_discovery_host(provisioning_host, module_discovery_sat, pxe_loader):
    """Fixture for returning a pxe-less discovery host for provisioning"""
    sat = module_discovery_sat.sat
    image_name = f"{gen_string('alpha')}-{module_discovery_sat.iso}"
    mac = provisioning_host.provisioning_nic_mac_addr
    # Remaster and upload discovery image to automatically input values
    result = sat.execute(
        'cd /var/www/html/pub && '
        f'discovery-remaster {module_discovery_sat.iso} '
        f'"proxy.type=foreman proxy.url=https://{sat.hostname}:443 fdi.pxmac={mac} fdi.pxauto=1"'
    )
    pattern = re.compile(r"foreman-discovery-image\S+")
    fdi = pattern.findall(result.stdout)[0]
    Broker(
        workflow='import-disk-image',
        import_disk_image_name=image_name,
        import_disk_image_url=(f'https://{sat.hostname}/pub/{fdi}'),
        firmware_type=pxe_loader.vm_firmware,
    ).execute()
    # Change host to boot discovery image
    Broker(
        job_template='configure-pxe-boot',
        target_host=provisioning_host.name,
        target_vlan_id=settings.provisioning.vlan_id,
        target_vm_firmware=provisioning_host._broker_args['target_vm_firmware'],
        target_pxeless_image=image_name,
        target_boot_scenario='pxeless_pre',
    ).execute()
    yield provisioning_host
    Broker(workflow='remove-disk-image', remove_disk_image_name=image_name).execute()


@pytest.fixture
def configure_secureboot_provisioning(
    request, pxe_loader, module_provisioning_sat, module_provisioning_rhel_content
):
    """Fixture for configuring Secureboot pxe_loader for provisioning, when hosts RHEL version > Satellites RHEL version"""
    rhel_ver = module_provisioning_rhel_content.os.major
    sat = module_provisioning_sat.sat
    if (
        int(rhel_ver) > sat.os_version.major
        and pxe_loader.vm_firmware == 'uefi_secure_boot'
        and module_provisioning_sat.sat.network_type != NetworkType.IPV6
    ):
        # Set the path for the shim and GRUB2 binaries for the OS of host
        bootloader_path = '/var/lib/tftpboot/bootloader-universe/pxegrub2/redhat/default/x86_64'

        # Create the directory to store the shim and GRUB2 binaries for the OS of host
        sat.execute(f'install -o foreman-proxy -g foreman-proxy -d {bootloader_path}')

        # Fetch and Download SB packages, and extract Shim/Grub2 binaries
        for prefix in ['grub2-efi-x64', 'shim-x64']:
            url = sat.get_secureboot_packages_with_version(
                f'{settings.repos.get(f"rhel{rhel_ver}_os").baseos}/Packages', prefix
            )
            sat.execute(f'curl -o /tmp/{prefix}.rpm {url}')
            sat.execute(f'rpm2cpio /tmp/{prefix}.rpm | cpio -idv --directory /tmp')

        # Make the shim and GRUB2 binaries available for host provisioning:
        sat.execute(f'cp /tmp/boot/efi/EFI/redhat/grubx64.efi {bootloader_path}/grubx64.efi')
        sat.execute(f'cp /tmp/boot/efi/EFI/redhat/shimx64.efi {bootloader_path}/shimx64.efi')
        sat.execute(f'ln -sr {bootloader_path}/grubx64.efi {bootloader_path}/boot.efi')
        sat.execute(f'ln -sr {bootloader_path}/shimx64.efi {bootloader_path}/boot-sb.efi')
        sat.execute(f'chmod 644 {bootloader_path}/grubx64.efi {bootloader_path}/shimx64.efi')
        yield
        sat.execute(f'rm -rf {bootloader_path}')
    else:
        yield None
