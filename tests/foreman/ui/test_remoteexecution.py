"""Test class for Job Invocation procedure

:Requirement: Remoteexecution

:CaseAutomation: Automated

:CaseComponent: RemoteExecution

:Team: Endeavour

:CaseImportance: High

"""

from collections import OrderedDict
import datetime
import time

from inflection import camelize
import pytest
from wait_for import wait_for

from robottelo.config import settings
from robottelo.constants import ANY_CONTEXT
from robottelo.utils.datafactory import (
    gen_string,
    valid_hostgroups_list_short,
)


def test_positive_hostgroups_full_nested_names(
    module_org,
    smart_proxy_location,
    target_sat,
):
    """Check that full host group names are displayed when invoking a job

    :id: 2301cd1d-ed82-4168-9f9b-d1661ac8fc5b

    :steps:

        1. Go to Monitor -> Jobs -> Run job
        2. In "Target hosts and inputs" step, choose "Host groups" targeting

    :expectedresults: Verify that in the dropdown, full hostgroup names are present, e.g. Parent/Child/Grandchild

    :parametrized: yes

    :customerscenario: true

    :BZ: 2209968
    """
    names = valid_hostgroups_list_short()
    tree = OrderedDict(
        {
            'parent1': {'name': names[0], 'parent': None},
            'parent2': {'name': names[1], 'parent': None},
            'child1a': {'name': names[2], 'parent': 'parent1'},
            'child1b': {'name': names[3], 'parent': 'parent1'},
            'child2': {'name': names[4], 'parent': 'parent2'},
            'grandchild1a1': {'name': names[5], 'parent': 'child1a'},
            'grandchild1a2': {'name': names[6], 'parent': 'child1a'},
            'grandchild1b': {'name': names[7], 'parent': 'child1b'},
        }
    )
    expected_names = []
    for identifier, data in tree.items():
        name = data['name']
        parent_name = None if data['parent'] is None else tree[data['parent']]['name']
        target_sat.cli_factory.hostgroup(
            {
                'name': name,
                'parent': parent_name,
                'organization-ids': module_org.id,
                'location-ids': smart_proxy_location.id,
            }
        )
        expected_name = ''
        current = identifier
        while current:
            expected_name = (
                f"{tree[current]['name']}/{expected_name}"
                if expected_name
                else tree[current]['name']
            )
            current = tree[current]['parent']
        # we should have something like "parent1/child1a"
        expected_names.append(expected_name)

    with target_sat.ui_session() as session:
        session.organization.select(module_org.name)
        session.location.select(smart_proxy_location.name)
        hostgroups = session.jobinvocation.read_hostgroups()

    for name in expected_names:
        assert name in hostgroups


@pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
def test_positive_run_default_job_template(
    session,
    target_sat,
    rex_contenthost,
    module_org,
):
    """Run a job template on a host

    :id: a21eac46-1a22-472d-b4ce-66097159a868

    :Setup: Use pre-defined job template.

    :steps:

        1. Get contenthost with rex enabled
        2. Navigate to an individual host and click Run Job
        3. Select the job and appropriate template
        4. Run the job

    :expectedresults: Verify the job was successfully ran against the host, check also using the job widget on the main dashboard

    :parametrized: yes

    :bz: 1898656, 2182353

    :customerscenario: true
    """

    hostname = rex_contenthost.hostname

    with target_sat.ui_session() as session:
        session.organization.select(module_org.name)
        assert session.host.search(hostname)[0]['Name'] == hostname
        command = 'ls'
        session.jobinvocation.run(
            {
                'category_and_template.job_category': 'Commands',
                'category_and_template.job_template_text_input': 'Run Command - Script Default',
                'target_hosts_and_inputs.targetting_type': 'Hosts',
                'target_hosts_and_inputs.targets': hostname,
                'target_hosts_and_inputs.command': command,
            }
        )
        session.jobinvocation.wait_job_invocation_state(entity_name='Run ls', host_name=hostname)
        status = session.jobinvocation.read(entity_name='Run ls', host_name=hostname)
        assert status['overview']['hosts_table'][0]['Status'] == 'Succeeded'

        # check status also on the job dashboard
        job_name = f'Run {command}'
        jobs = session.dashboard.read('LatestJobs')['jobs']
        success_jobs = [job for job in jobs if job['State'] == 'succeeded']
        assert len(success_jobs) > 0
        assert job_name in [job['Name'] for job in success_jobs]


@pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
def test_rex_through_host_details(session, target_sat, rex_contenthost, module_org):
    """Run remote execution using the new host details page

    :id: ee625595-4995-43b2-9e6d-633c9b33ff93

    :steps:
        1. Navigate to Overview tab
        2. Schedule a job
        3. Wait for the job to finish
        4. Job is visible in Recent jobs card

    :expectedresults: Remote execution succeeded and the job is visible on Recent jobs card on
        Overview tab
    """

    hostname = rex_contenthost.hostname

    job_args = {
        'category_and_template.job_category': 'Commands',
        'category_and_template.job_template_text_input': 'Run Command - Script Default',
        'target_hosts_and_inputs.command': 'ls',
    }
    with target_sat.ui_session() as session:
        session.organization.select(module_org.name)
        session.host_new.schedule_job(hostname, job_args)
        task_result = target_sat.wait_for_tasks(
            search_query=(f'Remote action: Run ls on {hostname}'),
            search_rate=2,
            max_tries=30,
        )
        task_status = target_sat.api.ForemanTask(id=task_result[0].id).poll()
        assert task_status['result'] == 'success'
        recent_jobs = session.host_new.get_details(hostname, "overview.recent_jobs")['overview']
        assert recent_jobs['recent_jobs']['finished']['table'][0]['column0'] == "Run ls"
        assert recent_jobs['recent_jobs']['finished']['table'][0]['column2'] == "succeeded"


@pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
@pytest.mark.parametrize(
    'ui_user', [{'admin': True}, {'admin': False}], indirect=True, ids=['adminuser', 'nonadminuser']
)
def test_positive_run_custom_job_template(
    session, module_org, default_location, target_sat, ui_user, rex_contenthost
):
    """Run a job template on a host

    :id: 3a59eb15-67c4-46e1-ba5f-203496ec0b0c

    :Setup: Create a working job template.

    :steps:

        1. Set remote_execution_connect_by_ip on host to true
        2. Navigate to an individual host and click Run Job
        3. Select the job and appropriate template
        4. Run the job

    :expectedresults: Verify the job was successfully ran against the host

    :parametrized: yes

    :bz: 2220965

    :customerscenario: true
    """

    hostname = rex_contenthost.hostname
    ui_user.location.append(target_sat.api.Location(id=default_location.id))
    ui_user.update(['location'])
    job_template_name = gen_string('alpha')
    with target_sat.ui_session() as session:
        session.organization.select(module_org.name)
        assert session.host.search(hostname)[0]['Name'] == hostname
        session.jobtemplate.create(
            {
                'template.name': job_template_name,
                'template.template_editor.rendering_options': 'Editor',
                'template.template_editor.editor': '<%= input("command") %>',
                'job.provider_type': 'Script',
                'inputs': [{'name': 'command', 'required': True, 'input_type': 'User input'}],
            }
        )
        assert session.jobtemplate.search(job_template_name)[0]['Name'] == job_template_name
        session.jobinvocation.run(
            {
                'category_and_template.job_category': 'Miscellaneous',
                'category_and_template.job_template_text_input': job_template_name,
                'target_hosts_and_inputs.targets': hostname,
                'target_hosts_and_inputs.command': 'ls',
            }
        )
        job_description = f'{camelize(job_template_name.lower())} with inputs command="ls"'
        session.jobinvocation.wait_job_invocation_state(
            entity_name=job_description, host_name=hostname
        )
        status = session.jobinvocation.read(entity_name=job_description, host_name=hostname)
        assert status['overview']['hosts_table'][0]['Status'] == 'Succeeded'


@pytest.mark.upgrade
@pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
def test_positive_run_job_template_multiple_hosts(
    session, module_org, target_sat, rex_contenthosts
):
    """Run a job template against multiple hosts

    :id: c4439ec0-bb80-47f6-bc31-fa7193bfbeeb

    :Setup: Create a working job template.

    :steps:

        1. Set remote_execution_connect_by_ip on hosts to true
        2. Navigate to the hosts page and select at least two hosts
        3. Click the "Select Action"
        4. Select the job and appropriate template
        5. Run the job

    :expectedresults: Verify the job was successfully ran against the hosts
    """

    host_names = []
    for vm in rex_contenthosts:
        host_names.append(vm.hostname)
        vm.configure_rex(satellite=target_sat, org=module_org)
    with target_sat.ui_session() as session:
        session.organization.select(module_org.name)
        for host in host_names:
            assert session.host.search(host)[0]['Name'] == host
        session.host.reset_search()
        job_status = session.host.schedule_remote_job(
            host_names,
            {
                'category_and_template.job_category': 'Commands',
                'category_and_template.job_template_text_input': 'Run Command - Script Default',
                'target_hosts_and_inputs.command': 'sleep 5',
            },
        )
        assert job_status['overview']['job_status'] == 'Success'
        assert {host_job['Host'] for host_job in job_status['overview']['hosts_table']} == set(
            host_names
        )
        assert all(
            host_job['Status'] == 'success' for host_job in job_status['overview']['hosts_table']
        )


@pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
def test_positive_run_scheduled_job_template_by_ip(session, module_org, rex_contenthost):
    """Schedule a job to be ran against a host by ip

    :id: 4387bed9-969d-45fb-80c2-b0905bb7f1bd

    :Setup: Use pre-defined job template.

    :steps:

        1. Set remote_execution_connect_by_ip on host to true
        2. Navigate to an individual host and click Run Job
        3. Select the job and appropriate template
        4. Select "Schedule future execution"
        5. Enter a desired time for the job to run
        6. Click submit

    :expectedresults:

        1. Verify the job was not immediately ran
        2. Verify the job was successfully ran after the designated time

    :parametrized: yes
    """
    job_time = 6 * 60
    hostname = rex_contenthost.hostname
    with session:
        session.organization.select(module_org.name)
        session.location.select('Default Location')
        assert session.host.search(hostname)[0]['Name'] == hostname
        plan_time = session.browser.get_client_datetime() + datetime.timedelta(seconds=job_time)
        command_to_run = 'sleep 10'
        job_status = session.host.schedule_remote_job(
            [hostname],
            {
                'category_and_template.job_category': 'Commands',
                'category_and_template.job_template_text_input': 'Run Command - Script Default',
                'target_hosts_and_inputs.command': command_to_run,
                'schedule.future': True,
                'schedule_future_execution.start_at_date': plan_time.strftime("%Y/%m/%d"),
                'schedule_future_execution.start_at_time': plan_time.strftime("%H:%M"),
            },
            wait_for_results=False,
        )
        # Note that to create this host scheduled job we spent some time from that plan_time, as it
        # was calculated before creating the job
        job_left_time = (plan_time - session.browser.get_client_datetime()).total_seconds()
        # assert that we have time left to wait, otherwise we have to use more job time,
        # the job_time must be significantly greater than job creation time.
        assert job_left_time > 0
        assert job_status['overview']['hosts_table'][0]['Host'] == hostname
        assert job_status['overview']['hosts_table'][0]['Status'] in ('Awaiting start', 'N/A')
        # sleep 3/4 of the left time
        time.sleep(job_left_time * 3 / 4)
        job_status = session.jobinvocation.read(
            f'Run {command_to_run}', hostname, 'overview.hosts_table'
        )
        assert job_status['overview']['hosts_table'][0]['Host'] == hostname
        assert job_status['overview']['hosts_table'][0]['Status'] in (
            'Awaiting start',
            'N/A',
            'Succeeded',
        )
        # recalculate the job left time to be more accurate
        job_left_time = (plan_time - session.browser.get_client_datetime()).total_seconds()
        # the last read time should not take more than 1/4 of the last left time
        assert job_left_time > 0
        wait_for(
            lambda: session.jobinvocation.read(
                f'Run {command_to_run}', hostname, 'overview.hosts_table'
            )['overview']['hosts_table'][0]['Status']
            == 'running',
            timeout=(job_left_time + 30),
            delay=1,
        )
        # wait the job to change status to "success"
        wait_for(
            lambda: session.jobinvocation.read(
                f'Run {command_to_run}', hostname, 'overview.hosts_table'
            )['overview']['hosts_table'][0]['Status']
            == 'Succeeded',
            timeout=30,
            delay=1,
        )
        job_status = session.jobinvocation.read(f'Run {command_to_run}', hostname, 'overview')
        assert job_status['overview']['job_status'] == 'Success'
        assert job_status['overview']['hosts_table'][0]['Host'] == hostname
        assert job_status['overview']['hosts_table'][0]['Status'] == 'Succeeded'


@pytest.mark.rhel_ver_list([settings.content_host.default_rhel_version])
@pytest.mark.usefixtures('setting_update')
@pytest.mark.parametrize('setting_update', ['lab_features=true'], indirect=True)
def test_positive_check_job_invocation_details_page(target_sat, rex_contenthost):
    """
    Run a remote job and check the job invocations detail page for correct values.

    :id: 7d201a52-5db1-11ef-98e6-000c29a0e355

    :steps:
        1. Run a successful remote job on one host.
        2. Check the result data on the new job invocation details page.

    :expectedresults:
        1. It should report the job name in the title.
        2. It should report the correct numbers in Succeeded, Failed, In Progress and Cancelled fields.
        3. It should report correct information, like, template name that was used, host search query,
            organization, location and command.

    :CaseImportance: High

    :Verifies: SAT-18427, SAT-26605

    :parametrized: yes
    """
    client = rex_contenthost

    correlation_id = gen_string("alphanumeric").lower()
    command = f'echo {correlation_id}'
    job_name = f'Run {command}'
    template_name = 'Run Command - Script Default'
    host_search_query = f'name = {client.hostname}'
    jobs_succeeded = 1
    total_hosts = 1

    template_id = (
        target_sat.api.JobTemplate().search(query={'search': f'name="{template_name}"'})[0].id
    )
    job = target_sat.api.JobInvocation().run(
        synchronous=False,
        data={
            'job_template_id': template_id,
            'organization': ANY_CONTEXT['org'],
            'location': ANY_CONTEXT['location'],
            'inputs': {
                'command': command,
            },
            'targeting_type': 'static_query',
            'search_query': host_search_query,
        },
    )
    target_sat.wait_for_tasks(f'resource_type = JobInvocation and resource_id = {job["id"]}')
    result = target_sat.api.JobInvocation(id=job['id']).read()
    assert result.succeeded == jobs_succeeded

    with target_sat.ui_session() as session:
        status = session.jobinvocation.read(
            entity_name=job_name, host_name=client.hostname, new_ui=True
        )
        assert status['title'] == job_name
        assert status['overall_status']['succeeded_hosts'] == jobs_succeeded
        assert status['overall_status']['total_hosts'] == total_hosts
        assert status['status']['Succeeded'] == jobs_succeeded
        assert status['status']['Failed'] == 0
        assert status['status']['In Progress'] == 0
        assert status['status']['Cancelled'] == 0
        assert status['overview']['Template'] == template_name
        assert status['target_hosts']['search_query'] == host_search_query
        assert status['target_hosts']['data']['Organization'] == ANY_CONTEXT['org']
        assert status['target_hosts']['data']['Location'] == ANY_CONTEXT['location']
        assert status['user_inputs']['data']['command'] == command
