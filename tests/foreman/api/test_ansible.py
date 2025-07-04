"""Test class for Ansible Roles and Variables pages

:Requirement: Ansible

:CaseAutomation: Automated

:CaseComponent: Ansible-ConfigurationManagement

:Team: Endeavour

:CaseImportance: Critical

"""

from broker import Broker
from fauxfactory import gen_string
import pytest
from wait_for import wait_for

from robottelo.config import robottelo_tmp_dir, settings, user_nailgun_config
from robottelo.hosts import ContentHost
from robottelo.utils.issue_handlers import is_open


@pytest.fixture
def filtered_user(target_sat, module_org, module_location):
    """
    :steps:
        1. Create a role with a host view filtered
        2. Create a user with that role
        3. Setup a host
    """
    role = target_sat.api.Role(
        name=gen_string('alpha'), location=[module_location], organization=[module_org]
    ).create()
    # assign view_hosts (with a filter, to test BZ 1699188),
    # view_hostgroups, view_facts permissions to the role
    permission_hosts = target_sat.api.Permission().search(query={'search': 'name="view_hosts"'})
    permission_hostgroups = target_sat.api.Permission().search(
        query={'search': 'name="view_hostgroups"'}
    )
    permission_facts = target_sat.api.Permission().search(query={'search': 'name="view_facts"'})
    target_sat.api.Filter(
        permission=permission_hosts, search='name != nonexistent', role=role
    ).create()
    target_sat.api.Filter(permission=permission_hostgroups, role=role).create()
    target_sat.api.Filter(permission=permission_facts, role=role).create()

    password = gen_string('alpha')
    user = target_sat.api.User(
        role=[role], password=password, location=[module_location], organization=[module_org]
    ).create()

    return user, password


@pytest.mark.upgrade
class TestAnsibleCfgMgmt:
    """Test class for Configuration Management with Ansible

    :CaseComponent: Ansible-ConfigurationManagement

    """

    @pytest.mark.e2e
    def test_fetch_and_sync_ansible_playbooks(self, target_sat):
        """
        Test Ansible Playbooks api for fetching and syncing playbooks

        :id: 17b4e767-1494-4960-bc60-f31a0495c09f

        :steps:
            1. Install ansible collection with playbooks.
            2. Try to fetch the playbooks via api.
            3. Sync the playbooks.
            4. Assert the count of playbooks fetched and synced are equal.

        :expectedresults:
            1. Playbooks should be fetched and synced successfully.

        :BZ: 2115686

        :customerscenario: true
        """
        http_proxy = (
            f'HTTPS_PROXY={settings.http_proxy.HTTP_PROXY_IPv6_URL} '
            if not target_sat.network_type.has_ipv4
            else ''
        )
        assert (
            target_sat.execute(
                f'{http_proxy}ansible-galaxy collection install -p /usr/share/ansible/collections '
                'xprazak2.forklift_collection'
            ).status
            == 0
        )
        proxy_id = target_sat.nailgun_smart_proxy.id
        playbook_fetch = target_sat.api.AnsiblePlaybooks().fetch(data={'proxy_id': proxy_id})
        playbooks_count = len(playbook_fetch['results']['playbooks_names'])
        playbook_sync = target_sat.api.AnsiblePlaybooks().sync(data={'proxy_id': proxy_id})
        assert playbook_sync['action'] == "Sync playbooks"

        target_sat.wait_for_tasks(
            search_query=(f'id = {playbook_sync["id"]}'),
            poll_timeout=100,
        )
        task_details = target_sat.api.ForemanTask().search(
            query={'search': f'id = {playbook_sync["id"]}'}
        )
        assert task_details[0].result == 'success'
        assert len(task_details[0].output['result']['created']) == playbooks_count

    @pytest.mark.e2e
    def test_add_and_remove_ansible_role_hostgroup(self, target_sat):
        """
        Test add and remove functionality for ansible roles in hostgroup via API

        :id: 7672cf86-fa31-11ed-855a-0fd307d2d66b

        :steps:
            1. Create a hostgroup and a nested hostgroup
            2. Sync a few ansible roles
            3. Assign a few ansible roles with the host group
            4. Add some ansible role with the host group
            5. Add some ansible roles to the nested hostgroup
            6. Remove the added ansible roles from the parent and nested hostgroup

        :expectedresults:
            1. Ansible role assign/add/remove functionality should work as expected in API

        :BZ: 2164400
        """
        ROLE_NAMES = [
            'theforeman.foreman_scap_client',
            'redhat.satellite.hostgroups',
            'RedHatInsights.insights-client',
            'redhat.satellite.compute_resources',
        ]
        hg = target_sat.api.HostGroup(name=gen_string('alpha')).create()
        hg_nested = target_sat.api.HostGroup(name=gen_string('alpha'), parent=hg).create()
        proxy_id = target_sat.nailgun_smart_proxy.id
        target_sat.api.AnsibleRoles().sync(data={'proxy_id': proxy_id, 'role_names': ROLE_NAMES})
        ROLES = [
            target_sat.api.AnsibleRoles().search(query={'search': f'name={role}'})[0].id
            for role in ROLE_NAMES
        ]
        # Assign first 2 roles to HG and verify it
        target_sat.api.HostGroup(id=hg.id).assign_ansible_roles(
            data={'ansible_role_ids': ROLES[:2]}
        )
        for r1, r2 in zip(
            target_sat.api.HostGroup(id=hg.id).list_ansible_roles(), ROLE_NAMES[:2], strict=True
        ):
            assert r1['name'] == r2

        # Add next role from list to HG and verify it
        target_sat.api.HostGroup(id=hg.id).add_ansible_role(data={'ansible_role_id': ROLES[2]})
        for r1, r2 in zip(
            target_sat.api.HostGroup(id=hg.id).list_ansible_roles(), ROLE_NAMES[:3], strict=True
        ):
            assert r1['name'] == r2

        # Add next role to nested HG, and verify roles are also nested to HG along with assigned role
        # Also, ensure the parent HG does not contain the roles assigned to nested HGs
        target_sat.api.HostGroup(id=hg_nested.id).add_ansible_role(
            data={'ansible_role_id': ROLES[3]}
        )
        for r1, r2 in zip(
            target_sat.api.HostGroup(id=hg_nested.id).list_ansible_roles(),
            [ROLE_NAMES[-1]] + ROLE_NAMES[:-1],
            strict=True,
        ):
            assert r1['name'] == r2

        for r1, r2 in zip(
            target_sat.api.HostGroup(id=hg.id).list_ansible_roles(), ROLE_NAMES[:3], strict=True
        ):
            assert r1['name'] == r2

        # Remove roles assigned one by one from HG and nested HG
        for role in ROLES[:3]:
            target_sat.api.HostGroup(id=hg.id).remove_ansible_role(data={'ansible_role_id': role})
        hg_roles = target_sat.api.HostGroup(id=hg.id).list_ansible_roles()
        assert len(hg_roles) == 0

        for role in ROLES:
            target_sat.api.HostGroup(id=hg_nested.id).remove_ansible_role(
                data={'ansible_role_id': role}
            )
        hg_nested_roles = target_sat.api.HostGroup(id=hg_nested.id).list_ansible_roles()
        assert len(hg_nested_roles) == 0

    @pytest.mark.e2e
    def test_positive_ansible_roles_inherited_from_hostgroup(
        self, request, target_sat, module_org, module_location
    ):
        """Verify ansible roles inheritance functionality for host with parent/nested hostgroup via API

        :id: 7672cf86-fa31-11ed-855a-0fd307d2d66g

        :steps:
            1. Create a host, hostgroup and nested hostgroup
            2. Sync a few ansible roles
            3. Assign a few ansible roles to the host, hostgroup, nested hostgroup and verify it.
            4. Update host to be in parent/nested hostgroup and verify roles assigned

        :expectedresults:
            1. Hosts in parent/nested hostgroups must have direct and indirect roles correctly assigned.

        :BZ: 2187967

        :customerscenario: true
        """
        ROLE_NAMES = [
            'theforeman.foreman_scap_client',
            'RedHatInsights.insights-client',
            'redhat.satellite.compute_resources',
        ]
        proxy_id = target_sat.nailgun_smart_proxy.id
        host = target_sat.api.Host(organization=module_org, location=module_location).create()
        hg = target_sat.api.HostGroup(name=gen_string('alpha'), organization=[module_org]).create()
        hg_nested = target_sat.api.HostGroup(
            name=gen_string('alpha'), parent=hg, organization=[module_org]
        ).create()

        @request.addfinalizer
        def _finalize():
            host.delete()
            hg_nested.delete()
            hg.delete()

        target_sat.api.AnsibleRoles().sync(data={'proxy_id': proxy_id, 'role_names': ROLE_NAMES})
        ROLES = [
            target_sat.api.AnsibleRoles().search(query={'search': f'name={role}'})[0].id
            for role in ROLE_NAMES
        ]

        # Assign roles to Host/Hostgroup/Nested Hostgroup and verify it
        target_sat.api.Host(id=host.id).add_ansible_role(data={'ansible_role_id': ROLES[0]})
        assert ROLE_NAMES[0] == target_sat.api.Host(id=host.id).list_ansible_roles()[0]['name']

        target_sat.api.HostGroup(id=hg.id).add_ansible_role(data={'ansible_role_id': ROLES[1]})
        assert ROLE_NAMES[1] == target_sat.api.HostGroup(id=hg.id).list_ansible_roles()[0]['name']

        target_sat.api.HostGroup(id=hg_nested.id).add_ansible_role(
            data={'ansible_role_id': ROLES[2]}
        )
        listroles = target_sat.api.HostGroup(id=hg_nested.id).list_ansible_roles()
        assert ROLE_NAMES[2] == listroles[0]['name']
        assert listroles[0]['directly_assigned']
        assert ROLE_NAMES[1] == listroles[1]['name']
        assert not listroles[1]['directly_assigned']

        # Update host to be in nested hostgroup and verify roles assigned
        host.hostgroup = hg_nested
        host = host.update(['hostgroup'])
        listroles_host = target_sat.api.Host(id=host.id).list_ansible_roles()
        assert ROLE_NAMES[0] == listroles_host[0]['name']
        assert listroles_host[0]['directly_assigned']
        assert ROLE_NAMES[1] == listroles_host[1]['name']
        assert not listroles_host[1]['directly_assigned']
        assert ROLE_NAMES[2] == listroles_host[2]['name']
        assert not listroles_host[1]['directly_assigned']
        # Verify nested hostgroup doesn't contains the roles assigned to host
        listroles_nested_hg = target_sat.api.HostGroup(id=hg_nested.id).list_ansible_roles()
        assert ROLE_NAMES[0] not in [role['name'] for role in listroles_nested_hg]
        assert ROLE_NAMES[2] == listroles_nested_hg[0]['name']
        assert ROLE_NAMES[1] == listroles_nested_hg[1]['name']

        # Update host to be in parent hostgroup and verify roles assigned
        host.hostgroup = hg
        host = host.update(['hostgroup'])
        listroles = target_sat.api.Host(id=host.id).list_ansible_roles()
        assert ROLE_NAMES[0] == listroles[0]['name']
        assert listroles[0]['directly_assigned']
        assert ROLE_NAMES[1] == listroles[1]['name']
        assert not listroles[1]['directly_assigned']
        # Verify parent hostgroup doesn't contains the roles assigned to host
        listroles_hg = target_sat.api.HostGroup(id=hg.id).list_ansible_roles()
        assert ROLE_NAMES[0] not in [role['name'] for role in listroles_hg]
        assert ROLE_NAMES[1] == listroles_hg[0]['name']

    @pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
    def test_positive_read_facts_with_filter(
        self, request, target_sat, rex_contenthost, filtered_user, module_org, module_location
    ):
        """Read host's Ansible facts as a user with a role that has host filter

        :id: 483d5faf-7a4c-4cb7-b14f-369768ad99b0

        :steps:
            1. Run Ansible roles on a host
            2. Using API, read Ansible facts of that host

        :expectedresults: Ansible facts returned

        :BZ: 1699188

        :customerscenario: true
        """
        user, password = filtered_user
        host = rex_contenthost.nailgun_host
        host.organization = module_org
        host.location = module_location
        host.update(['organization', 'location'])
        if is_open('SAT-18656'):

            @request.addfinalizer
            def _finalize():
                target_sat.cli.Host.disassociate({'name': rex_contenthost.hostname})
                assert rex_contenthost.execute('subscription-manager unregister').status == 0
                assert rex_contenthost.execute('subscription-manager clean').status == 0
                target_sat.cli.Host.delete({'name': rex_contenthost.hostname})

        # gather ansible facts by running ansible roles on the host
        host.play_ansible_roles()
        wait_for(
            lambda: len(rex_contenthost.nailgun_host.get_facts()) > 0,
            timeout=30,
            delay=2,
        )
        user_cfg = user_nailgun_config(user.login, password)
        # get facts through API
        user_facts = (
            target_sat.api.Host(server_config=user_cfg)
            .search(query={'search': f'name={rex_contenthost.hostname}'})[0]
            .get_facts()
        )
        assert 'subtotal' in user_facts
        assert user_facts['subtotal'] == 1
        assert 'results' in user_facts
        assert rex_contenthost.hostname in user_facts['results']
        assert len(user_facts['results'][rex_contenthost.hostname]) > 0


class TestAnsibleREX:
    """Test class for remote execution via Ansible

    :CaseComponent: Ansible-RemoteExecution
    """

    @pytest.mark.e2e
    @pytest.mark.pit_client
    @pytest.mark.no_containers
    @pytest.mark.rhel_ver_match('[^6].*')
    def test_positive_ansible_job_on_host(
        self, target_sat, module_org, module_location, module_ak_with_synced_repo, rhel_contenthost
    ):
        """Test successful execution of Ansible Job on host.

        :id: c8dcdc54-cb98-4b24-bff9-049a6cc36acb

        :steps:
            1. Register a content host with satellite
            2. Import a role into satellite
            3. Assign that role to a host
            4. Assert that the role was assigned to the host successfully
            5. Run the Ansible playbook associated with that role
            6. Check if the job is executed.

        :expectedresults:
            1. Host should be assigned the proper role.
            2. Job execution must be successful.

        :BZ: 2164400
        """
        SELECTED_ROLE = 'RedHatInsights.insights-client'
        rhel_contenthost.enable_ipv6_dnf_and_rhsm_proxy()
        if rhel_contenthost.os_version.major <= 7:
            rhel_contenthost.create_custom_repos(rhel7=settings.repos.rhel7_os)
            assert rhel_contenthost.execute('yum install -y insights-client').status == 0
        result = rhel_contenthost.register(
            module_org, module_location, module_ak_with_synced_repo.name, target_sat
        )
        assert result.status == 0, f'Failed to register host: {result.stderr}'
        proxy_id = target_sat.nailgun_smart_proxy.id
        target_host = rhel_contenthost.nailgun_host
        target_sat.api.AnsibleRoles().sync(
            data={'proxy_id': proxy_id, 'role_names': [SELECTED_ROLE]}
        )
        role_id = (
            target_sat.api.AnsibleRoles().search(query={'search': f'name={SELECTED_ROLE}'})[0].id
        )
        target_sat.api.Host(id=target_host.id).add_ansible_role(data={'ansible_role_id': role_id})
        host_roles = target_host.list_ansible_roles()
        assert host_roles[0]['name'] == SELECTED_ROLE
        assert target_host.name == rhel_contenthost.hostname

        template_id = (
            target_sat.api.JobTemplate()
            .search(query={'search': 'name="Ansible Roles - Ansible Default"'})[0]
            .id
        )
        job = target_sat.api.JobInvocation().run(
            synchronous=False,
            data={
                'job_template_id': template_id,
                'targeting_type': 'static_query',
                'search_query': f'name = {rhel_contenthost.hostname}',
            },
        )
        target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}', poll_timeout=1000
        )
        result = target_sat.api.JobInvocation(id=job['id']).read()
        assert result.succeeded == 1
        target_sat.api.Host(id=target_host.id).remove_ansible_role(
            data={'ansible_role_id': role_id}
        )
        host_roles = target_host.list_ansible_roles()
        assert len(host_roles) == 0

    def test_positive_ansible_job_on_multiple_host(
        self,
        target_sat,
        module_org,
        module_location,
        module_ak_with_synced_repo,
    ):
        """Test execution of Ansible job on multiple hosts simultaneously.

        :id: 9369feef-466c-40d3-9d0d-65520d7f21ef

        :customerscenario: true

        :steps:
            1. Register multiple content hosts with satellite
            2. Import a role into satellite
            3. Assign that role to all host
            4. Trigger ansible job keeping all host in a single query
            5. Check the passing and failing of individual hosts
            6. Check if one of the job on a host is failed resulting into whole job is marked as failed.

        :expectedresults:
            1. One of the jobs failing on a single host must impact the overall result as failed.

        :BZ: 2167396, 2190464, 2184117
        """
        with Broker.multi_manager(
            rhel9={
                'host_class': ContentHost,
                'workflow': settings.server.deploy_workflows.os,
                'deploy_rhel_version': '9',
                'deploy_network_type': settings.server.network_type,
            },
            rhel8={
                'host_class': ContentHost,
                'workflow': settings.server.deploy_workflows.os,
                'deploy_rhel_version': '8',
                'deploy_network_type': settings.server.network_type,
            },
            rhel7={
                'host_class': ContentHost,
                'workflow': settings.server.deploy_workflows.os,
                'deploy_rhel_version': '7',
                'deploy_network_type': settings.server.network_type,
            },
        ) as multi_hosts:
            hosts = [multi_hosts['rhel9'][0], multi_hosts['rhel8'][0], multi_hosts['rhel7'][0]]
            SELECTED_ROLE = 'RedHatInsights.insights-client'
            for host in hosts:
                result = host.register(
                    module_org, module_location, module_ak_with_synced_repo.name, target_sat
                )
                assert result.status == 0, f'Failed to register host: {result.stderr}'
                proxy_id = target_sat.nailgun_smart_proxy.id
                target_host = host.nailgun_host
                target_sat.api.AnsibleRoles().sync(
                    data={'proxy_id': proxy_id, 'role_names': [SELECTED_ROLE]}
                )
                role_id = (
                    target_sat.api.AnsibleRoles()
                    .search(query={'search': f'name={SELECTED_ROLE}'})[0]
                    .id
                )
                target_sat.api.Host(id=target_host.id).add_ansible_role(
                    data={'ansible_role_id': role_id}
                )
                host_roles = target_host.list_ansible_roles()
                assert host_roles[0]['name'] == SELECTED_ROLE

            template_id = (
                target_sat.api.JobTemplate()
                .search(query={'search': 'name="Ansible Roles - Ansible Default"'})[0]
                .id
            )
            job = target_sat.api.JobInvocation().run(
                synchronous=False,
                data={
                    'job_template_id': template_id,
                    'targeting_type': 'static_query',
                    'search_query': f'name ^ ({hosts[0].hostname} && {hosts[1].hostname} '
                    f'&& {hosts[2].hostname})',
                },
            )
            target_sat.wait_for_tasks(
                f'resource_type = JobInvocation and resource_id = {job["id"]}',
                poll_timeout=1000,
                must_succeed=False,
            )
            result = target_sat.api.JobInvocation(id=job['id']).read()
            assert result.succeeded == 2  # SELECTED_ROLE working on rhel8/rhel9 clients
            assert result.failed == 1  # SELECTED_ROLE failing  on rhel7 client
            assert result.status_label == 'failed'

    @pytest.mark.no_containers
    @pytest.mark.rhel_ver_match(r'^(?!.*fips).*$')  # all major versions, excluding fips
    def test_positive_ansible_localhost_job_on_host(
        self, target_sat, module_org, module_location, module_ak_with_synced_repo, rhel_contenthost
    ):
        """Test successful execution of Ansible Job with "hosts: localhost" on host.

        :id: c8dcdc54-cb98-4b24-bff9-049a6cc36acd

        :steps:
            1. Register a content host with satellite
            2. Run the Ansible playbook with "hosts: localhost" on registered host
            3. Check if the job is executed and verify job output

        :expectedresults:
            1. Ansible playbook with "hosts: localhost" job execution must be successful.

        :BZ: 1982698

        :customerscenario: true
        """
        playbook = '''
            ---
            - name: Simple Ansible Playbook for Localhost
              hosts: localhost
              gather_facts: no
              tasks:
              - name: Print a message
                debug:
                  msg: "Hello, localhost!"
        '''
        result = rhel_contenthost.register(
            module_org, module_location, module_ak_with_synced_repo.name, target_sat
        )
        assert result.status == 0, f'Failed to register host: {result.stderr}'

        template_id = (
            target_sat.api.JobTemplate()
            .search(query={'search': 'name="Ansible - Run playbook"'})[0]
            .id
        )
        job = target_sat.api.JobInvocation().run(
            synchronous=False,
            data={
                'job_template_id': template_id,
                'targeting_type': 'static_query',
                'search_query': f'name = {rhel_contenthost.hostname}',
                'inputs': {'playbook': playbook},
            },
        )
        target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}', poll_timeout=1000
        )
        result = target_sat.api.JobInvocation(id=job['id']).read()
        assert result.pending == 0
        assert result.succeeded == 1
        assert result.status_label == 'succeeded'

        result = target_sat.api.JobInvocation(id=job['id']).outputs()['outputs'][0]['output']
        assert [i['output'] for i in result if '"msg": "Hello, localhost!"' in i['output']]
        assert [i['output'] for i in result if i['output'] == 'Exit status: 0']

    @pytest.mark.no_containers
    @pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
    def test_positive_ansible_job_timeout_to_kill(
        self, target_sat, module_org, module_location, module_ak_with_synced_repo, rhel_contenthost
    ):
        """when running ansible-playbook, timeout to kill/execution_timeout_interval setting
            is honored for registered host

        :id: a082f599-fbf7-4779-aa18-5139e2bce777

        :steps:
            1. Register a content host with satellite
            2. Run Ansible playbook to pause execution for a while, along with
                timeout to kill/execution_timeout_interval setting on the registered host
            3. Verify job is terminated honoring timeout to kill setting and verify job output.

        :expectedresults: Timeout to kill terminates the job if playbook doesn't finish in time

        :BZ: 1931489

        :customerscenario: true
        """
        playbook = '''
            ---
            - name: Sample Ansible Playbook to pause
              hosts: all
              gather_facts: no
              tasks:
              - name: Pause for 5 minutes
                pause:
                  minutes: 5
        '''
        result = rhel_contenthost.register(
            module_org, module_location, module_ak_with_synced_repo.name, target_sat
        )
        assert result.status == 0, f'Failed to register host: {result.stderr}'

        template_id = (
            target_sat.api.JobTemplate()
            .search(query={'search': 'name="Ansible - Run playbook"'})[0]
            .id
        )
        # run ansible-playbook with execution_timeout_interval/timeout_to_kill
        job = target_sat.api.JobInvocation().run(
            synchronous=False,
            data={
                'job_template_id': template_id,
                'targeting_type': 'static_query',
                'search_query': f'name = {rhel_contenthost.hostname}',
                'inputs': {'playbook': playbook},
                'execution_timeout_interval': '30',
            },
        )
        target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}',
            poll_timeout=1000,
            must_succeed=False,
        )
        result = target_sat.api.JobInvocation(id=job['id']).read()
        assert result.pending == 0
        assert result.failed == 1
        assert result.status_label == 'failed'

        result = target_sat.api.JobInvocation(id=job['id']).outputs()['outputs'][0]['output']
        termination_msg = 'Timeout for execution passed, stopping the job'
        assert [i['output'] for i in result if i['output'] == termination_msg]
        assert [i['output'] for i in result if i['output'] == 'StandardError: Job execution failed']
        assert [i['output'] for i in result if i['output'] == 'Exit status: 120']

    @pytest.mark.no_containers
    @pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
    def test_positive_ansible_job_privilege_escalation(
        self,
        target_sat,
        rhel_contenthost,
        module_org,
        module_location,
        module_ak_with_synced_repo,
    ):
        """Verify privilege escalation defined inside ansible playbook tasks is working
        when executing the playbook via Ansible - Remote Execution

        :id: 8c63fd1a-2121-4cce-9ec1-ae12817c9cc4

        :steps:
            1. Register a RHEL host to Satellite.
            2. Setup a user on that host.
            3. Create a playbook.
            4. Set the SSH user to the created user, and unset the Effective user.
            5. Run the playbook.

        :expectedresults: In the playbook, created user is expected instead root user.

        :BZ: 1955385

        :customerscenario: true
        """
        playbook = '''
            ---
            - name: Test Play
              hosts: all
              gather_facts: false
              tasks:
                - name: Check current user
                  command: bash -c "whoami"
                  register: def_user
                - debug:
                    var: def_user.stdout
                - name: Check become user
                  command: bash -c "whoami"
                  become: true
                  become_user: testing
                  register: bec_user
                - debug:
                    var: bec_user.stdout
        '''
        result = rhel_contenthost.register(
            module_org, module_location, module_ak_with_synced_repo.name, target_sat
        )
        assert result.status == 0, f'Failed to register host: {result.stderr}'
        assert rhel_contenthost.execute('useradd testing').status == 0
        pwd = rhel_contenthost.execute(
            f'echo {settings.server.ssh_password} | passwd testing --stdin'
        )
        assert 'passwd: all authentication tokens updated successfully.' in pwd.stdout
        template_id = (
            target_sat.api.JobTemplate()
            .search(query={'search': 'name="Ansible - Run playbook"'})[0]
            .id
        )
        job = target_sat.api.JobInvocation().run(
            synchronous=False,
            data={
                'job_category': 'Ansible Playbook',
                'job_template_id': template_id,
                'search_query': f'name = {rhel_contenthost.hostname}',
                'targeting_type': 'static_query',
                'inputs': {'playbook': playbook},
            },
        )
        target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}',
            poll_timeout=1000,
        )

        result = target_sat.api.JobInvocation(id=job['id']).read()
        assert result.pending == 0
        assert result.succeeded == 1
        assert result.status_label == 'succeeded'

        task = target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}',
        )
        assert '"def_user.stdout": "root"' in task[0].humanized['output']
        assert '"bec_user.stdout": "testing"' in task[0].humanized['output']

    @pytest.mark.no_containers
    @pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
    def test_positive_ansible_job_with_nonexisting_module(
        self, target_sat, module_org, module_location, module_ak_with_synced_repo, rhel_contenthost
    ):
        """Verify running ansible-playbook job with nonexisting_module, as a result the playbook fails,
        and the Ansible REX job fails on Satellite as well.

        :id: a082f599-fbf7-4779-aa18-5139e2bce888

        :steps:
            1. Register a content host with satellite
            2. Run Ansible playbook with nonexisting_module
            3. Verify playbook fails and the Ansible REX job fails on Satellite

        :expectedresults: Satellite job fails with the error and non-zero exit status,
            when using a playbook with the nonexisting_module module.

        :BZ: 2107577, 2028112

        :customerscenario: true
        """
        playbook = '''
            ---
            - name: Playbook with a failing task
              hosts: localhost
              gather_facts: no
              tasks:
              - name: Run a non-existing module
                nonexisting_module: ""
        '''
        result = rhel_contenthost.register(
            module_org, module_location, module_ak_with_synced_repo.name, target_sat
        )
        assert result.status == 0, f'Failed to register host: {result.stderr}'

        template_id = (
            target_sat.api.JobTemplate()
            .search(query={'search': 'name="Ansible - Run playbook"'})[0]
            .id
        )
        # run ansible-playbook with nonexisting_module
        job = target_sat.api.JobInvocation().run(
            synchronous=False,
            data={
                'job_template_id': template_id,
                'targeting_type': 'static_query',
                'search_query': f'name = {rhel_contenthost.hostname}',
                'inputs': {'playbook': playbook},
                'execution_timeout_interval': '30',
            },
        )
        target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}',
            poll_timeout=1000,
            must_succeed=False,
        )
        result = target_sat.api.JobInvocation(id=job['id']).read()
        assert result.pending == 0
        assert result.failed == 1
        assert result.status_label == 'failed'
        result = target_sat.api.JobInvocation(id=job['id']).outputs()['outputs'][0]['output']
        termination_msg = 'ERROR! couldn\'t resolve module/action \'nonexisting_module\''
        assert [i['output'] for i in result if termination_msg in i['output']]
        assert [i['output'] for i in result if i['output'] == 'StandardError: Job execution failed']
        assert [i['output'] for i in result if i['output'] == 'Exit status: 4']

    @pytest.mark.no_containers
    @pytest.mark.parametrize('ansible_check_mode', ['True', 'False'], ids=['enabled', 'disabled'])
    @pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
    def test_positive_ansible_job_with_check_mode(
        self,
        request,
        target_sat,
        module_org,
        module_location,
        module_ak_with_synced_repo,
        rhel_contenthost,
        ansible_check_mode,
    ):
        """Verify the Ansible REX job runs with check mode enabled,
        to see what changes it would make without applying them.

        :id: a082f599-fbf7-4779-aa18-5139e2bce999

        :steps:
            1. Register a content host with satellite
            2. Clone the "Ansible Roles - Ansible Default" Job Template.
            3. Enable "Ansible Check Mode Enabled" on the cloned Job Template.
            4. Create a custom role to validate ansible check mode, and assign it to the host
            5. Schedule a Job on host and select the cloned Job Category and Job Template.
            6. Validate REX job runs in check mode to preview changes without applying them.

        :expectedresults: Ansible REX job works without any errors and,
            when ansible_check_mode_enabled it previews changes without applying them.

        :verifies: SAT-32223
        """
        data = """---
        - name: Inform if running in check mode
          debug:
            msg: "Check mode is enabled. No changes will be applied."
          when: ansible_check_mode

        - name: Inform if running in normal (non-check) mode
          debug:
            msg: "Check mode is not enabled. Changes will be applied."
          when: not ansible_check_mode

        - name: Attempt to create a test file (only in non-check mode)
          file:
            path: /tmp/check_mode_test_file
            state: touch
          when: not ansible_check_mode

        - name: Note on file creation task behavior when in check mode
          debug:
            msg: "File creation task is conditionally skipped or executed based on check mode."
          when: ansible_check_mode
        """
        role_name = gen_string('alpha')
        role_task_file = f'{robottelo_tmp_dir}/playbook.yml'
        with open(role_task_file, 'w') as f:
            f.write(data)
        target_sat.put(role_task_file, f'/etc/ansible/roles/{role_name}/tasks/main.yml')

        # Register contenthost and assign the custom role
        result = rhel_contenthost.register(
            module_org, module_location, module_ak_with_synced_repo.name, target_sat
        )
        assert result.status == 0, f'Failed to register host: {result.stderr}'

        proxy_id = target_sat.nailgun_smart_proxy.id
        target_host = rhel_contenthost.nailgun_host
        target_sat.api.AnsibleRoles().sync(data={'proxy_id': proxy_id, 'role_names': [role_name]})
        role_id = target_sat.api.AnsibleRoles().search(query={'search': f'name={role_name}'})[0].id
        target_sat.api.Host(id=target_host.id).add_ansible_role(data={'ansible_role_id': role_id})
        host_roles = target_host.list_ansible_roles()
        assert host_roles[0]['name'] == role_name

        ## Clone the template and update it to enable Ansible Check Mode
        default_template_name = 'Ansible Roles - Ansible Default'
        template = target_sat.api.JobTemplate().search(
            query={'search': f'name="{default_template_name}"'}
        )[0]

        if ansible_check_mode == 'True':
            cloned_template_name = gen_string('alpha')
            template.clone(data={'name': cloned_template_name})
            template = target_sat.api.JobTemplate().search(
                query={'search': f'name="{cloned_template_name}"'}
            )[0]
            request.addfinalizer(template.delete)
            template.ansible_check_mode = True
            template.update(['ansible_check_mode'])

        # run ansible-playbook with ansible_check_mode_enabled
        job = target_sat.api.JobInvocation().run(
            synchronous=False,
            data={
                'job_template_id': template.id,
                'targeting_type': 'static_query',
                'search_query': f'name = {rhel_contenthost.hostname}',
                'execution_timeout_interval': '30',
            },
        )
        target_sat.wait_for_tasks(
            f'resource_type = JobInvocation and resource_id = {job["id"]}',
            poll_timeout=1000,
            must_succeed=False,
        )
        result = target_sat.api.JobInvocation(id=job['id']).read()
        assert result.pending == 0
        assert result.succeeded == 1
        assert result.status_label == 'succeeded'

        result = target_sat.api.JobInvocation(id=job['id']).outputs()['outputs'][0]['output']
        check_mode_msg = (
            'Check mode is enabled' if ansible_check_mode == 'True' else 'Check mode is not enabled'
        )
        assert [i['output'] for i in result if check_mode_msg in i['output']]
        check_file_present = rhel_contenthost.execute('test -f /tmp/check_mode_test_file')
        assert check_file_present.status == (1 if ansible_check_mode == 'True' else 0)
