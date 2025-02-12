"""Flatpak related tests being run through CLI.

:Requirement: Repository

:CaseAutomation: Automated

:CaseComponent: Repositories

:team: Phoenix-content

:CaseImportance: High

"""

import pytest
import requests

from robottelo.config import settings
from robottelo.constants import FLATPAK_INDEX_SUFFIX, FLATPAK_REMOTES, PULPCORE_FLATPAK_ENDPOINT
from robottelo.exceptions import CLIReturnCodeError
from robottelo.utils.datafactory import gen_string


@pytest.fixture
def function_role(target_sat):
    """An empty Role, no permissions"""
    role = target_sat.api.Role().create()
    yield role
    role.delete()


@pytest.fixture
def function_user(target_sat, function_role, function_org):
    """Non-admin user with an empty role assigned."""
    password = gen_string('alphanumeric')
    user = target_sat.api.User(
        login=gen_string('alpha'),
        password=password,
        role=[function_role],
        organization=[function_org],
    ).create()
    user.password = password
    yield user
    user.delete()


def test_CRUD_and_sync_flatpak_remote_with_permissions(
    target_sat, function_user, function_role, function_org
):
    """Verify that Flatpak remote can be created, read, updated, scanned and deleted
        only with appropriate permissions.

    :id: 3a8df09f-49bf-498f-8d71-7c0c3b4c505d

    :setup:
        1. Non-admin user with an empty role (no permissions yet) assigned.

    :steps:
        Ensure that Flatpak remote can be
        1. listed only with proper permissions.
        2. created only with proper permissions.
        3. updated and scanned only with proper permissions.
        4. deleted only with proper permissions.

    :expectedresults:
        1. Every action succeeds only with the proper permission.
        2. The required permission is mentioned in the error message correctly.

    """
    emsg = 'Missing one of the required permissions: {}'
    usr, pwd = function_user.login, function_user.password

    # 1. Ensure that remotes can be listed only with proper permissions.
    p = 'view_flatpak_remotes'
    with pytest.raises(CLIReturnCodeError) as e:
        target_sat.cli.FlatpakRemote().with_user(usr, pwd).list()
    assert emsg.format(p) in str(e)

    target_sat.api_factory.create_role_permissions(function_role, {'Katello::FlatpakRemote': [p]})
    res = (
        target_sat.cli.FlatpakRemote()
        .with_user(usr, pwd)
        .list({'organization-id': function_org.id})
    )
    assert len(res) == 0, f'Expected no remotes yet in the {function_org.name} org, but got {res}'

    # 2. Ensure that remotes can be created only with proper permissions.
    p = 'create_flatpak_remotes'
    with pytest.raises(CLIReturnCodeError) as e:
        target_sat.cli.FlatpakRemote().with_user(usr, pwd).create(
            {
                'organization-id': function_org.id,
                'url': FLATPAK_REMOTES['Fedora']['url'],
                'name': gen_string('alpha'),
            }
        )
    assert emsg.format(p) in str(e)

    target_sat.api_factory.create_role_permissions(function_role, {'Katello::FlatpakRemote': [p]})
    remote = (
        target_sat.cli.FlatpakRemote()
        .with_user(usr, pwd)
        .create(
            {
                'organization-id': function_org.id,
                'url': FLATPAK_REMOTES['Fedora']['url'],
                'name': gen_string('alpha'),
            }
        )
    )
    res = (
        target_sat.cli.FlatpakRemote()
        .with_user(usr, pwd)
        .info({'organization-id': function_org.id, 'name': remote['name']})
    )
    assert res == remote, 'Read values differ from the created ones'

    # 3. Ensure that remotes can be updated and scanned only with proper permissions.
    p = 'edit_flatpak_remotes'
    desc = gen_string('alpha')
    with pytest.raises(CLIReturnCodeError) as e:
        target_sat.cli.FlatpakRemote().with_user(usr, pwd).update(
            {'organization-id': function_org.id, 'name': remote['name'], 'description': desc}
        )
    assert emsg.format(p) in str(e)
    with pytest.raises(CLIReturnCodeError) as e:
        target_sat.cli.FlatpakRemote().with_user(usr, pwd).scan(
            {'organization-id': function_org.id, 'name': remote['name']}
        )
    assert emsg.format(p) in str(e)

    target_sat.api_factory.create_role_permissions(function_role, {'Katello::FlatpakRemote': [p]})
    target_sat.cli.FlatpakRemote().with_user(usr, pwd).update(
        {'organization-id': function_org.id, 'name': remote['name'], 'description': desc}
    )
    target_sat.cli.FlatpakRemote().with_user(usr, pwd).scan(
        {'organization-id': function_org.id, 'name': remote['name']}
    )
    res = (
        target_sat.cli.FlatpakRemote()
        .with_user(usr, pwd)
        .info({'organization-id': function_org.id, 'name': remote['name']})
    )
    assert res['description'] == desc, 'Description was not updated'
    assert 'http' in res['registry-url'], 'Scan of flatpak remote failed'

    # 4. Ensure that remotes can be deleted only with proper permissions.
    p = 'destroy_flatpak_remotes'
    with pytest.raises(CLIReturnCodeError) as e:
        target_sat.cli.FlatpakRemote().with_user(usr, pwd).delete(
            {'organization-id': function_org.id, 'name': remote['name']}
        )
    assert emsg.format(p) in str(e)

    target_sat.api_factory.create_role_permissions(function_role, {'Katello::FlatpakRemote': [p]})
    res = (
        target_sat.cli.FlatpakRemote()
        .with_user(usr, pwd)
        .delete({'organization-id': function_org.id, 'name': remote['name']})
    )
    assert 'Flatpak Remote deleted' in res
    with pytest.raises(CLIReturnCodeError) as e:
        target_sat.cli.FlatpakRemote().with_user(usr, pwd).info(
            {'organization-id': function_org.id, 'name': remote['name']}
        )
    assert 'Error: flatpak_remote not found' in str(e)


@pytest.mark.parametrize('function_flatpak_remote', ['RedHat', 'Fedora'], indirect=True)
def test_scan_flatpak_remote(target_sat, function_org, function_flatpak_remote):
    """Verify flatpak remote scan detects all repos available in the remote index.

    :id: 3dff23f3-f415-4fb2-a41c-7cdcae617bb0

    :parametrized: yes

    :setup:
        1. Create a flatpak remote and scan it.

    :steps:
        1. Read the remote index via its API.
        2. Compare the scanned repos match the repos in the remote index.

    :expectedresults:
        1. Repos scanned by flatpak remote match the repos available in the remote index.

    """
    scanned_repo_names = [item['name'] for item in function_flatpak_remote.repos]

    # 1. Read the remote index via its API.
    rq = requests.get(
        f'{function_flatpak_remote.remote["flatpak-index-url"]}/{FLATPAK_INDEX_SUFFIX}'
    ).json()
    index_repo_names = [item['Name'] for item in rq['Results']]

    # 2. Compare the scanned repos match the repos in the remote index.
    assert sorted(scanned_repo_names) == sorted(index_repo_names)


@pytest.mark.upgrade
def test_flatpak_pulpcore_endpoint(target_sat):
    """Ensure the Satellite's flatpak pulpcore endpoint is up after install or upgrade.

    :id: 3593ac46-4e5d-495e-95eb-d9609cb46a15

    :steps:
        1. Hit Satellite's pulpcore_registry endpoint.

    :expectedresults:
        1. HTTP 200
    """
    rq = requests.get(PULPCORE_FLATPAK_ENDPOINT.format(target_sat.hostname), verify=False)
    assert rq.ok, f'Expected 200 but got {rq.status_code} from pulpcore registry index'


@pytest.mark.e2e
@pytest.mark.upgrade
@pytest.mark.parametrize('function_flatpak_remote', ['RedHat'], indirect=True)
def test_sync_consume_flatpak_repo_via_library(
    request,
    module_target_sat,
    module_flatpak_contenthost,
    function_org,
    function_product,
    function_flatpak_remote,
):
    """Verify flatpak repository workflow end to end.

    :id: 06043b3e-be9b-4444-96b1-d3d15b7e3d8c

    :parametrized: yes

    :setup:
        1. Create a flatpak remote and scan it.

    :steps:
        1. Mirror flatpak repositories and sync them.
        2. Create an AK assigned to the Library.
        3. Register a content host using the AK.
        4. Configure the contenthost via REX to use Satellite's flatpak index.
        5. Install flatpak app from the repo via REX on the contenthost.
        6. Ensure the app has been installed successfully.

    :expectedresults:
        1. Entire workflow works and allows user to install a flatpak app at the registered
           contenthost.

    """
    sat, host = module_target_sat, module_flatpak_contenthost

    # 1. Mirror flatpak repositories and sync them.
    repo_names = ['rhel9/firefox-flatpak', 'rhel9/flatpak-runtime']  # runtime is dependency
    remote_repos = [r for r in function_flatpak_remote.repos if r['name'] in repo_names]
    for repo in remote_repos:
        sat.cli.FlatpakRemote().repository_mirror(
            {
                'flatpak-remote-id': function_flatpak_remote.remote['id'],
                'id': repo['id'],  # or by name
                'product-id': function_product.id,
            }
        )
        local_repo = sat.cli.Repository.list(
            {'product-id': function_product.id, 'name': repo['name']}
        )[0]
        sat.cli.Repository.synchronize({'id': local_repo['id']})
        assert 'latest' in sat.api.Repository(id=local_repo['id']).read().include_tags
        assert all(
            'flatpak' in m['content_type']
            for m in sat.api.Repository(id=local_repo['id']).docker_manifests()['results']
        )
        assert all(
            'index' in ml['content_type']
            for ml in sat.api.Repository(id=local_repo['id']).docker_manifest_lists()['results']
        )
    local_repos = sat.cli.Repository.list({'product-id': function_product.id})
    assert set([r['name'] for r in local_repos]) == set(repo_names), (
        'Required repo(s) were not scanned or mirrored'
    )

    # 2. Create an AK assigned to the Library.
    ak_lib = sat.cli.ActivationKey.create(
        {
            'name': gen_string('alpha'),
            'organization-id': function_org.id,
            'lifecycle-environment': 'Library',
            'content-view': 'Default Organization View',
        }
    )

    # 3. Register a content host using the AK.
    res = host.register(function_org, None, ak_lib['name'], sat, force=True)
    assert res.status == 0, (
        f'Failed to register host: {host.hostname}\nStdOut: {res.stdout}\nStdErr: {res.stderr}'
    )
    assert host.subscribed

    # 4. Configure the contenthost via REX to use Satellite's flatpak index.
    remote_name = f'SAT-remote-{gen_string("alpha")}'
    job = module_target_sat.cli_factory.job_invocation(
        {
            'organization': function_org.name,
            'job-template': 'Flatpak - Set up remote on host',
            'inputs': (
                f'Remote Name={remote_name}, '
                f'Flatpak registry URL=https://{sat.hostname}/pulpcore_registry/, '
                f'Username={settings.server.admin_username}, '
                f'Password={settings.server.admin_password}'
            ),
            'search-query': f"name ~ {host.hostname}",
        }
    )
    res = module_target_sat.cli.JobInvocation.info({'id': job.id})
    assert 'succeeded' in res['status']
    request.addfinalizer(lambda: host.execute(f'flatpak remote-delete {remote_name}'))

    # 5. Install flatpak app from the repo via REX on the contenthost.
    res = host.execute('flatpak remotes')
    assert remote_name in res.stdout

    app_name = 'Firefox'  # or 'org.mozilla.Firefox'
    res = host.execute('flatpak remote-ls')
    assert app_name in res.stdout

    job = module_target_sat.cli_factory.job_invocation(
        {
            'organization': function_org.name,
            'job-template': 'Flatpak - Install application on host',
            'inputs': f'Flatpak remote name={remote_name}, Application name={app_name}',
            'search-query': f"name ~ {host.hostname}",
        }
    )
    res = module_target_sat.cli.JobInvocation.info({'id': job.id})
    assert 'succeeded' in res['status']
    request.addfinalizer(
        lambda: host.execute(f'flatpak uninstall {remote_name} {app_name} com.redhat.Platform -y')
    )

    # 6. Ensure the app has been installed successfully.
    res = host.execute('flatpak list')
    assert app_name in res.stdout
