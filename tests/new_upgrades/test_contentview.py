"""Test for Content View related Upgrade Scenario's

:Requirement: UpgradedSatellite

:CaseAutomation: Automated

:CaseComponent: ContentViews

:Team: Phoenix-content

:CaseImportance: High

"""

from box import Box
from fauxfactory import gen_alpha
import pytest

from robottelo.config import settings
from robottelo.constants import RPM_TO_UPLOAD, DataFile
from robottelo.utils.shared_resource import SharedResource


@pytest.fixture
def cv_upgrade_setup(content_upgrade_shared_satellite, upgrade_action):
    """Pre-upgrade scenario that creates content-view with various repositories.

    :id: preupgrade-a4ebbfa1-106a-4962-9c7c-082833879ae8

    :steps:
        1. Create custom repositories of yum and file type.
        2. Create content-view.
        3. Add yum and file repositories in the content view.
        4. Publish the content-view.

    :expectedresults: Content-view created with various repositories.
    """
    target_sat = content_upgrade_shared_satellite
    with SharedResource(target_sat.hostname, upgrade_action, target_sat=target_sat) as sat_upgrade:
        test_data = Box(
            {
                'target_sat': target_sat,
                'cv': None,
                'org': None,
                'product': None,
                'yum_repo': None,
                'file_repo': None,
            }
        )
        test_name = f'cv_upgrade_{gen_alpha()}'  # unique name for the test
        org = target_sat.api.Organization(name=f'{test_name}_org').create()
        test_data.org = org
        product = target_sat.api.Product(organization=org, name=f'{test_name}_prod').create()
        test_data.product = product
        yum_repository = target_sat.api.Repository(
            product=product,
            name=f'{test_name}_yum_repo',
            url=settings.repos.yum_1.url,
            content_type='yum',
        ).create()
        test_data.yum_repo = yum_repository
        target_sat.api.Repository.sync(yum_repository)
        file_repository = target_sat.api.Repository(
            product=product, name=f'{test_name}_file_repo', content_type='file'
        ).create()
        test_data.file_repo = file_repository
        remote_file_path = f'/tmp/{RPM_TO_UPLOAD}'
        target_sat.put(DataFile.RPM_TO_UPLOAD, remote_file_path)
        file_repository.upload_content(files={'content': DataFile.RPM_TO_UPLOAD.read_bytes()})
        assert 'content' in file_repository.files()['results'][0]['name']
        cv = target_sat.publish_content_view(org, [yum_repository, file_repository], test_name)
        assert len(cv.read_json()['versions']) == 1
        test_data.cv = cv
        sat_upgrade.ready()
        target_sat._session = None
        yield test_data


@pytest.mark.content_upgrades
def test_cv_upgrade_scenario(cv_upgrade_setup):
    """After upgrade, the existing content-view(created before upgrade) should be updated.

    :id: postupgrade-a4ebbfa1-106a-4962-9c7c-082833879ae8

    :steps:
        1. Check yum and file repository which was added in CV before upgrade.
        2. Check the content view which was was created before upgrade.
        3. Remove yum repository from existing CV.
        4. Create new yum repository in existing CV.
        5. Publish content-view

    :expectedresults: After upgrade,
        1. All the repositories should be intact.
        2. Content view created before upgrade should be intact.
        3. The new repository should be added/updated to the CV.

    """
    target_sat = cv_upgrade_setup.target_sat
    org = target_sat.api.Organization().search(
        query={'search': f'name="{cv_upgrade_setup.org.name}"'}
    )[0]
    product = target_sat.api.Product(organization=org.id).search(
        query={'search': f'name="{cv_upgrade_setup.product.name}"'}
    )[0]
    cv = target_sat.api.ContentView(organization=org.id).search(
        query={'search': f'name="{cv_upgrade_setup.cv.name}"'}
    )[0]
    target_sat.api.Repository(organization=org.id).search(
        query={'search': f'name="{cv_upgrade_setup.yum_repo.name}"'}
    )[0]
    target_sat.api.Repository(organization=org.id).search(
        query={'search': f'name="{cv_upgrade_setup.file_repo.name}"'}
    )[0]
    cv.repository = []
    cv.update(['repository'])
    assert len(cv.read_json()['repositories']) == 0

    yum_repository2 = target_sat.api.Repository(
        product=product,
        name='cv_upgrade_yum_repos2',
        url=settings.repos.yum_2.url,
        content_type='yum',
    ).create()
    yum_repository2.sync()
    cv.repository = [yum_repository2]
    cv.update(['repository'])
    assert cv.read_json()['repositories'][0]['name'] == yum_repository2.name

    cv.publish()
    assert len(cv.read_json()['versions']) == 2
    content_view_json = cv.read_json()['environments'][0]
    cv.delete_from_environment(content_view_json['id'])
    assert len(cv.read_json()['environments']) == 0
