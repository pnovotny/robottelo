"""Test class for Virtwho Configure UI

:Requirement: Virt-whoConfigurePlugin

:CaseAutomation: Automated

:CaseLevel: Acceptance

:CaseComponent: Virt-whoConfigurePlugin

:Team: Phoenix

:TestType: Functional

:Upstream: No
"""
from fauxfactory import gen_string
import pytest

from robottelo.config import settings
from robottelo.utils.virtwho import (
    deploy_configure_by_command,
    deploy_configure_by_script,
    get_configure_command,
    get_configure_file,
    get_configure_id,
    get_configure_option,
)


@pytest.fixture()
def form_data():
    form = {
        'debug': True,
        'interval': 'Every hour',
        'hypervisor_id': 'hostname',
        'hypervisor_type': settings.virtwho.libvirt.hypervisor_type,
        'hypervisor_content.server': settings.virtwho.libvirt.hypervisor_server,
        'hypervisor_content.username': settings.virtwho.libvirt.hypervisor_username,
    }
    return form


@pytest.fixture()
def virtwho_config(form_data, target_sat, session_sca):
    name = gen_string('alpha')
    form_data['name'] = name
    with session_sca:
        session_sca.virtwho_configure.create(form_data)
        yield virtwho_config
        session_sca.virtwho_configure.delete(name)
        assert not session_sca.virtwho_configure.search(name)


class TestVirtwhoConfigforLibvirt:
    @pytest.mark.tier2
    @pytest.mark.parametrize('deploy_type', ['id', 'script'])
    def test_positive_deploy_configure_by_id_script(
        self, module_sca_manifest_org, virtwho_config, session_sca, form_data, deploy_type
    ):
        """Verify configure created and deployed with id.

        :id: 401cfc74-6cde-4ae1-bf03-b77a7528575c

        :expectedresults:
            1. Config can be created and deployed by command or script
            2. No error msg in /var/log/rhsm/rhsm.log
            3. Report is sent to satellite
            4. Virtual sku can be generated and attached
            5. Config can be deleted

        :CaseLevel: Integration

        :CaseImportance: High
        """
        name = form_data['name']
        values = session_sca.virtwho_configure.read(name)
        if deploy_type == "id":
            command = values['deploy']['command']
            deploy_configure_by_command(
                command,
                form_data['hypervisor_type'],
                debug=True,
                org=module_sca_manifest_org.label,
            )
        elif deploy_type == "script":
            script = values['deploy']['script']
            deploy_configure_by_script(
                script,
                form_data['hypervisor_type'],
                debug=True,
                org=module_sca_manifest_org.label,
            )
        assert session_sca.virtwho_configure.search(name)[0]['Status'] == 'ok'

    @pytest.mark.tier2
    def test_positive_hypervisor_id_option(
        self, module_sca_manifest_org, virtwho_config, session_sca, form_data
    ):
        """Verify Hypervisor ID dropdown options.

        :id: 24012fb0-b940-4a9f-bce8-9e43fdb50d82

        :expectedresults:
            1. hypervisor_id can be changed in virt-who-config-{}.conf if the
            dropdown option is selected to uuid/hwuuid/hostname.

        :CaseLevel: Integration

        :CaseImportance: Medium
        """
        name = form_data['name']
        config_id = get_configure_id(name)
        config_command = get_configure_command(config_id, module_sca_manifest_org.name)
        config_file = get_configure_file(config_id)
        values = ['uuid', 'hostname']
        for value in values:
            session_sca.virtwho_configure.edit(name, {'hypervisor_id': value})
            results = session_sca.virtwho_configure.read(name)
            assert results['overview']['hypervisor_id'] == value
            deploy_configure_by_command(
                config_command, form_data['hypervisor_type'], org=module_sca_manifest_org.label
            )
            assert get_configure_option('hypervisor_id', config_file) == value
