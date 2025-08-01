"""Tests for the Container Management Content

:Requirement: ContainerImageManagement

:CaseAutomation: Automated

:Team: Phoenix-content

:CaseComponent: ContainerImageManagement

"""

from fauxfactory import gen_string
import pytest
from wait_for import wait_for

from robottelo.config import settings
from robottelo.constants import (
    REPO_TYPE,
)
from robottelo.logging import logger


def _repo(sat, product_id, name=None, upstream_name=None, url=None):
    """Creates a Docker-based repository.

    :param product_id: ID of the ``Product``.
    :param str name: Name for the repository. If ``None`` then a random
        value will be generated.
    :param str upstream_name: A valid name of an existing upstream repository.
        If ``None`` then defaults to settings.container.upstream_name constant.
    :param str url: URL of repository. If ``None`` then defaults to
        settings.container.registry_hub constant.
    :return: A ``Repository`` object.
    """
    return sat.cli_factory.make_repository(
        {
            'content-type': REPO_TYPE['docker'],
            'docker-upstream-name': upstream_name or settings.container.upstream_name,
            'name': name or gen_string('alpha', 5),
            'product-id': product_id,
            'url': url or settings.container.registry_hub,
        }
    )


class TestDockerClient:
    """Tests specific to using ``Docker`` as a client to pull Docker images
    from a Satellite 6 instance.

    :CaseImportance: Medium
    """

    def test_positive_pull_image(
        self, request, module_org, module_container_contenthost, target_sat
    ):
        """A Docker-enabled client can use ``docker pull`` to pull a
        Docker image off a Satellite 6 instance.

        :id: 023f0538-2aad-4f87-b8a8-6ccced648366

        :steps:

            1. Publish and promote content view with Docker content
            2. Register Docker-enabled client against Satellite 6.

        :expectedresults: Client can pull Docker images from server and run it.

        :parametrized: yes
        """
        product = target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})
        repo = _repo(target_sat, product['id'])
        target_sat.cli.Repository.synchronize({'id': repo['id']})
        repo = target_sat.cli.Repository.info({'id': repo['id']})
        try:
            result = module_container_contenthost.execute(
                f'docker login -u {settings.server.admin_username}'
                f' -p {settings.server.admin_password} {target_sat.hostname}'
            )
            assert result.status == 0
            request.addfinalizer(
                lambda: module_container_contenthost.execute(f'docker logout {target_sat.hostname}')
            )

            # publishing takes few seconds sometimes
            result, _ = wait_for(
                lambda: module_container_contenthost.execute(f'docker pull {repo["published-at"]}'),
                num_sec=60,
                delay=2,
                fail_condition=lambda out: out.status != 0,
                logger=logger,
            )
            assert result.status == 0
            try:
                result = module_container_contenthost.execute(f'docker run {repo["published-at"]}')
                assert result.status == 0
            finally:
                # Stop and remove the container
                result = module_container_contenthost.execute(
                    f'docker ps -a | grep {repo["published-at"]}'
                )
                container_id = result.stdout[0].split()[0]
                module_container_contenthost.execute(f'docker stop {container_id}')
                module_container_contenthost.execute(f'docker rm {container_id}')
        finally:
            # Remove docker image
            module_container_contenthost.execute(f'docker rmi {repo["published-at"]}')

    @pytest.mark.skip_if_not_set('docker')
    @pytest.mark.e2e
    def test_positive_container_admin_end_to_end_search(
        self, request, module_org, module_container_contenthost, target_sat
    ):
        """Verify that docker command line can be used against
        Satellite server to search for container images stored
        on Satellite instance.

        :id: cefa74e1-e40d-4f47-853b-1268643cea2f

        :steps:

            1. Publish and promote content view with Docker content
            2. Set 'Unauthenticated Pull' option to false
            3. Try to search for docker images on Satellite
            4. Use Docker client to login to Satellite docker hub
            5. Search for docker images
            6. Use Docker client to log out of Satellite docker hub
            7. Try to search for docker images (ensure last search result
               is caused by change of Satellite option and not login/logout)
            8. Set 'Unauthenticated Pull' option to true
            9. Search for docker images

        :expectedresults: Client can search for docker images stored
            on Satellite instance

        :parametrized: yes
        """
        pattern_prefix = gen_string('alpha', 5)
        registry_name_pattern = (
            f'{pattern_prefix}-<%= content_view.label %>/<%= repository.docker_upstream_name %>'
        )

        # Satellite setup: create product and add Docker repository;
        # create content view and add Docker repository;
        # create lifecycle environment and promote content view to it
        lce = target_sat.cli_factory.make_lifecycle_environment({'organization-id': module_org.id})
        product = target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})
        repo = _repo(target_sat, product['id'], upstream_name=settings.container.upstream_name)
        target_sat.cli.Repository.synchronize({'id': repo['id']})
        content_view = target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = target_sat.cli.ContentView.info({'id': content_view['id']})
        target_sat.cli.ContentView.version_promote(
            {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )
        target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-name-pattern': registry_name_pattern,
                'registry-unauthenticated-pull': 'false',
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )
        docker_repo_uri = (
            f'{target_sat.hostname}/{pattern_prefix}-{content_view["label"]}/'
            f'{settings.container.upstream_name}'
        ).lower()

        # 3. Try to search for docker images on Satellite
        remote_search_command = (
            f'docker search {target_sat.hostname}/{settings.container.upstream_name}'
        )
        result = module_container_contenthost.execute(remote_search_command)
        assert result.status == 0
        assert docker_repo_uri not in result.stdout

        # 4. Use Docker client to login to Satellite docker hub
        result = module_container_contenthost.execute(
            f'docker login -u {settings.server.admin_username}'
            f' -p {settings.server.admin_password} {target_sat.hostname}'
        )
        assert result.status == 0
        request.addfinalizer(
            lambda: module_container_contenthost.execute(f'docker logout {target_sat.hostname}')
        )

        # 5. Search for docker images
        result = module_container_contenthost.execute(remote_search_command)
        assert result.status == 0
        assert docker_repo_uri in result.stdout

        # 6. Use Docker client to log out of Satellite docker hub
        result = module_container_contenthost.execute(f'docker logout {target_sat.hostname}')
        assert result.status == 0

        # 7. Try to search for docker images
        result = module_container_contenthost.execute(remote_search_command)
        assert result.status == 0
        assert docker_repo_uri not in result.stdout

        # 8. Set 'Unauthenticated Pull' option to true
        target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-unauthenticated-pull': 'true',
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )

        # 9. Search for docker images
        result = module_container_contenthost.execute(remote_search_command)
        assert result.status == 0
        assert docker_repo_uri in result.stdout

    @pytest.mark.skip_if_not_set('docker')
    @pytest.mark.e2e
    def test_positive_container_admin_end_to_end_pull(
        self, request, module_org, module_container_contenthost, target_sat
    ):
        """Verify that docker command line can be used against
        Satellite server to pull in container images stored
        on Satellite instance.

        :id: 2a331f88-406b-4a5c-ae70-302a9994077f

        :steps:

            1. Publish and promote content view with Docker content
            2. Set 'Unauthenticated Pull' option to false
            3. Try to pull in docker image from Satellite
            4. Use Docker client to login to Satellite container registry
            5. Pull in docker image
            6. Use Docker client to log out of Satellite container registry
            7. Try to pull in docker image (ensure next pull result
               is caused by change of Satellite option and not login/logout)
            8. Set 'Unauthenticated Pull' option to true
            9. Pull in docker image

        :expectedresults: Client can pull in docker images stored
            on Satellite instance

        :parametrized: yes
        """
        pattern_prefix = gen_string('alpha', 5)
        docker_upstream_name = settings.container.upstream_name
        registry_name_pattern = (
            f'{pattern_prefix}-<%= content_view.label %>/<%= repository.docker_upstream_name %>'
        )

        # Satellite setup: create product and add Docker repository;
        # create content view and add Docker repository;
        # create lifecycle environment and promote content view to it
        lce = target_sat.cli_factory.make_lifecycle_environment({'organization-id': module_org.id})
        product = target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})
        repo = _repo(target_sat, product['id'], upstream_name=docker_upstream_name)
        target_sat.cli.Repository.synchronize({'id': repo['id']})
        content_view = target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = target_sat.cli.ContentView.info({'id': content_view['id']})
        target_sat.cli.ContentView.version_promote(
            {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )
        target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-name-pattern': registry_name_pattern,
                'registry-unauthenticated-pull': 'false',
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )
        docker_repo_uri = (
            f'{target_sat.hostname}/{pattern_prefix}-{content_view["label"]}/{docker_upstream_name}'
        ).lower()

        # 3. Try to pull in docker image from Satellite
        docker_pull_command = f'docker pull {docker_repo_uri}'
        result = module_container_contenthost.execute(docker_pull_command)
        assert result.status != 0

        # 4. Use Docker client to login to Satellite docker hub
        result = module_container_contenthost.execute(
            f'docker login -u {settings.server.admin_username}'
            f' -p {settings.server.admin_password} {target_sat.hostname}'
        )
        assert result.status == 0
        request.addfinalizer(
            lambda: module_container_contenthost.execute(f'docker logout {target_sat.hostname}')
        )

        # 5. Pull in docker image
        # publishing takes few seconds sometimes
        result, _ = wait_for(
            lambda: module_container_contenthost.execute(docker_pull_command),
            num_sec=60,
            delay=2,
            fail_condition=lambda out: out.status != 0,
            logger=logger,
        )
        assert result.status == 0

        # 6. Use Docker client to log out of Satellite docker hub
        result = module_container_contenthost.execute(f'docker logout {target_sat.hostname}')
        assert result.status == 0

        # 7. Try to pull in docker image
        result = module_container_contenthost.execute(docker_pull_command)
        assert result.status != 0

        # 8. Set 'Unauthenticated Pull' option to true
        target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-unauthenticated-pull': 'true',
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )

        # 9. Pull in docker image
        result = module_container_contenthost.execute(docker_pull_command)
        assert result.status == 0

    def test_positive_pull_content_with_longer_name(
        self, request, target_sat, module_container_contenthost, module_org
    ):
        """Verify that long name CV publishes when CV & docker repo both have a larger name.

        :id: e0ac0be4-f5ff-4a88-bb29-33aa2d874f46

        :steps:

            1. Create Product, docker repo, CV and LCE with a long name
            2. Sync the repos
            3. Add repository to CV, Publish, and then Promote CV to LCE
            4. Pull in docker image

        :expectedresults:

            1. Long Product, repository, CV and LCE should create successfully
            2. Sync repository successfully
            3. Publish & Promote should success
            4. Can pull in docker images

        :BZ: 2127470

        :customerscenario: true
        """
        pattern_postfix = gen_string('alpha', 10).lower()

        product_name = f'containers-{pattern_postfix}'
        repo_name = f'repo-{pattern_postfix}'
        lce_name = f'lce-{pattern_postfix}'
        cv_name = f'cv-{pattern_postfix}'

        # 1. Create Product, docker repo, CV and LCE with a long name
        product = target_sat.cli_factory.make_product_wait(
            {'name': product_name, 'organization-id': module_org.id}
        )

        repo = _repo(
            target_sat,
            product['id'],
            name=repo_name,
            upstream_name=settings.container.upstream_name,
        )

        # 2. Sync the repos
        target_sat.cli.Repository.synchronize({'id': repo['id']})

        lce = target_sat.cli_factory.make_lifecycle_environment(
            {'name': lce_name, 'organization-id': module_org.id}
        )
        cv = target_sat.cli_factory.make_content_view(
            {'name': cv_name, 'composite': False, 'organization-id': module_org.id}
        )

        # 3. Add repository to CV, Publish, and then Promote CV to LCE
        target_sat.cli.ContentView.add_repository({'id': cv['id'], 'repository-id': repo['id']})

        target_sat.cli.ContentView.publish({'id': cv['id']})
        cv = target_sat.cli.ContentView.info({'id': cv['id']})
        target_sat.cli.ContentView.version_promote(
            {'id': cv['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )

        podman_pull_command = (
            f"podman pull --tls-verify=false {target_sat.hostname}/{module_org.label}"
            f"/{lce['label']}/{cv['label']}/{product['label']}/{repo_name}".lower()
        )

        # 4. Pull in docker image
        assert (
            module_container_contenthost.execute(
                f'podman login -u {settings.server.admin_username}'
                f' -p {settings.server.admin_password} {target_sat.hostname}'
            ).status
            == 0
        )
        request.addfinalizer(
            lambda: module_container_contenthost.execute(f'podman logout {target_sat.hostname}')
        )

        assert module_container_contenthost.execute(podman_pull_command).status == 0

    @pytest.mark.e2e
    @pytest.mark.parametrize('gr_certs_setup', [False, True], ids=['manual-setup', 'GR-setup'])
    def test_podman_cert_auth(
        self, request, module_target_sat, module_org, module_container_contenthost, gr_certs_setup
    ):
        """Verify the podman search and pull works with cert-based
        authentication without need for login.

        :id: 7b1a457c-ae67-4a76-9f67-9074ea7f858a

        :parametrized: yes

        :Verifies: SAT-33254, SAT-33255

        :steps:
            1. Create and sync a docker repo.
            2. Create a CV with the repo, publish and promote it to a LCE.
            3. Create activation key for the LCE/CV and register a content host.
            4. Configure podman certs for authentication (manual setup only).
            5. Try podman search all, ensure Library and repo images are not listed.
            6. Try podman search/pull for Library images, ensure it fails.
            7. Try podman search/pull for the LCE/CV, ensure it works.

        :expectedresults:
            1. Podman search/pull is restricted for Library (or any LCE missing in AK).
            2. Podman search/pull works for environments included in AK.

        """
        sat, host = module_target_sat, module_container_contenthost

        # 1. Create and sync a docker repo.
        product = sat.cli_factory.make_product_wait({'organization-id': module_org.id})
        repo = _repo(sat, product['id'], upstream_name='quay/busybox', url='https://quay.io')
        sat.cli.Repository.synchronize({'id': repo['id']})

        # 2. Create a CV with the repo, publish and promote it to a LCE.
        cv = sat.cli_factory.make_content_view(
            {'organization-id': module_org.id, 'repository-ids': [repo['id']]}
        )
        sat.cli.ContentView.publish({'id': cv['id']})
        cv = sat.cli.ContentView.info({'id': cv['id']})
        lce = sat.cli_factory.make_lifecycle_environment({'organization-id': module_org.id})
        sat.cli.ContentView.version_promote(
            {'id': cv['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )

        # 3. Create activation key for the LCE/CV and register a content host.
        ak = sat.cli.ActivationKey.create(
            {
                'name': gen_string('alpha'),
                'organization-id': module_org.id,
                'lifecycle-environment-id': lce['id'],
                'content-view-id': cv['id'],
            }
        )
        res = host.register(
            module_org, None, ak['name'], sat, force=True, setup_container_certs=gr_certs_setup
        )
        assert res.status == 0
        assert host.subscribed

        @request.addfinalizer
        def _finalize():
            host.unregister()
            host.delete_host_record()

        # 4. Configure podman certs for authentication (manual setup only).
        if not gr_certs_setup:
            host.configure_podman_cert_auth(sat)
            request.addfinalizer(lambda: host.reset_podman_cert_auth(sat))

        # 5. Try podman search all, ensure Library and repo images are not listed.
        org_prefix = f'{sat.hostname}/{module_org.label}'
        lib_path = f'{org_prefix}/library'.lower()
        repo_path = f'{org_prefix}/{product.label}/{repo.label}'.lower()
        cv_path = f'{org_prefix}/{lce.label}/{cv["label"]}/{product.label}/{repo.label}'.lower()

        finds = host.execute(f'podman search {sat.hostname}/').stdout
        assert lib_path not in finds
        assert repo_path not in finds
        assert cv_path in finds
        paths = [f.strip() for f in finds.split('\n') if 'NAME' not in f and len(f)]
        assert len(paths) == 1

        # 6. Try podman search/pull for Library images, ensure it fails.
        for path in [lib_path, repo_path]:
            assert host.execute(f'podman search {path}').stdout == ''
            assert host.execute(f'podman pull {path}').status

        # 7. Try podman search/pull for the LCE/CV, ensure it works.
        res = host.execute(f'podman search {cv_path}')
        assert cv_path in res.stdout
        res = host.execute(f'podman pull {cv_path}')
        assert res.status == 0
        request.addfinalizer(lambda: host.execute(f'podman rmi {cv_path}'))
        res = host.execute('podman images')
        assert cv_path in res.stdout
