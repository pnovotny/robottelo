"""Test class for Locations UI

:Requirement: Location

:CaseAutomation: Automated

:CaseComponent: OrganizationsandLocations

:Team: Endeavour

:CaseImportance: High

"""

from fauxfactory import gen_ipaddr, gen_string
import pytest

from robottelo.config import settings
from robottelo.constants import ANY_CONTEXT, INSTALL_MEDIUM_URL, LIBVIRT_RESOURCE_URL


@pytest.mark.e2e
@pytest.mark.upgrade
def test_positive_end_to_end(session, target_sat):
    """Perform end to end testing for location component

    :id: dba5d94d-0c18-4db0-a9e8-66599bffc5d9

    :expectedresults: All expected CRUD actions finished successfully

    :CaseImportance: Critical
    """
    loc_parent = target_sat.api.Location().create()
    loc_child_name = gen_string('alpha')
    description = gen_string('alpha')
    updated_name = gen_string('alphanumeric')

    # create entities
    ip_addres = gen_ipaddr(ip3=True)
    subnet = target_sat.api.Subnet(network=ip_addres, mask='255.255.255.0').create()
    subnet_name = f'{subnet.name} ({subnet.network}/{subnet.cidr})'
    domain = target_sat.api.Domain().create()
    user = target_sat.api.User().create()
    media = target_sat.api.Media(
        path_=INSTALL_MEDIUM_URL % gen_string('alpha', 6), os_family='Redhat'
    ).create()

    with session:
        session.location.create(
            {
                'name': loc_child_name,
                'parent_location': loc_parent.name,
                'description': description,
            }
        )
        location_name = f"{loc_parent.name}/{loc_child_name}"
        loc_values = session.location.read(location_name)
        assert loc_values['primary']['parent_location'] == loc_parent.name
        assert loc_values['primary']['name'] == loc_child_name
        assert loc_values['primary']['description'] == description

        # assign entities
        session.location.update(
            location_name,
            {
                'primary.name': updated_name,
                'subnets.resources.assigned': [subnet_name],
                'domains.resources.assigned': [domain.name],
                'users.resources.assigned': [user.login],
                'media.resources.assigned': [media.name],
            },
        )
        location_name = f"{loc_parent.name}/{updated_name}"
        loc_values = session.location.read(location_name)
        assert loc_values['subnets']['resources']['assigned'][0] == subnet_name
        assert loc_values['domains']['resources']['assigned'][0] == domain.name
        assert loc_values['users']['resources']['assigned'][0] == user.login
        assert loc_values['media']['resources']['assigned'][0] == media.name

        # unassign entities
        session.location.update(
            location_name,
            {
                'subnets.resources.unassigned': [subnet_name],
                'domains.resources.unassigned': [domain.name],
                'users.resources.unassigned': [user.login],
                'media.resources.unassigned': [media.name],
            },
        )
        loc_values = session.location.read(location_name)
        assert len(loc_values['subnets']['resources']['assigned']) == 0
        assert subnet_name in loc_values['subnets']['resources']['unassigned']
        assert len(loc_values['domains']['resources']['assigned']) == 0
        assert domain.name in loc_values['domains']['resources']['unassigned']
        assert len(loc_values['users']['resources']['assigned']) == 0
        assert user.login in loc_values['users']['resources']['unassigned']
        assert len(loc_values['media']['resources']['assigned']) == 0
        assert media.name in loc_values['media']['resources']['unassigned']

        # delete location
        session.location.delete(location_name)
        assert not session.location.search(location_name)


def test_positive_create_with_all_users(session, target_sat):
    """Create location and do not add user to it. Check
    'all users' setting.

    :id: 6596962b-8fd0-4a82-bf54-fa6a31147311

    :customerscenario: true

    :expectedresults: User is visible in selected location

    :BZ: 1479736

    :Verifies: SAT-25386

    :BlockedBy: SAT-25386
    """
    user = target_sat.api.User().create()
    loc = target_sat.api.Location().create()
    with session:
        session.organization.select(org_name=ANY_CONTEXT['org'])
        session.location.select(loc_name=loc.name)
        session.location.update(loc.name, {'users.all_users': True})
        found_users = session.user.search(user.login)
        assert user.login in [user['Username'] for user in found_users]
        # SAT-25386 closed wontdo
        # user_values = session.user.read(user.login)
        # assert loc.name in user_values['locations']['resources']['assigned']


def test_positive_add_org_hostgroup_template(session, target_sat):
    """Add a organization, hostgroup, provisioning template by using
       the location name

    :id: 27d56d64-6866-46b6-962d-1ac2a11ae136

    :expectedresults: organization, hostgroup, provisioning template are
        added to location
    """
    org = target_sat.api.Organization().create()
    loc = target_sat.api.Location().create()
    hostgroup = target_sat.api.HostGroup().create()
    template = target_sat.api.ProvisioningTemplate().create()
    with session:
        session.location.update(
            loc.name,
            {
                'organizations.resources.assigned': [org.name],
                'host_groups.all_hostgroups': False,
                'host_groups.resources.unassigned': [hostgroup.name],
                'provisioning_templates.all_templates': False,
                'provisioning_templates.resources.unassigned': [template.name],
            },
        )
        loc_values = session.location.read(loc.name)
        assert loc_values['organizations']['resources']['assigned'][0] == org.name
        assert hostgroup.name in loc_values['host_groups']['resources']['unassigned']
        assert template.name in loc_values['provisioning_templates']['resources']['unassigned']
        session.location.update(
            loc.name,
            {
                'host_groups.resources.assigned': [hostgroup.name],
                'provisioning_templates.resources.assigned': [template.name],
            },
        )
        loc_values = session.location.read(loc.name)
        assert hostgroup.name in loc_values['host_groups']['resources']['assigned']
        assert template.name in loc_values['provisioning_templates']['resources']['assigned']


@pytest.mark.skip_if_not_set('libvirt')
def test_positive_update_compresource(session, target_sat):
    """Add/Remove compute resource from/to location

    :id: 1d24414a-666d-490d-89b9-cd0704684cdd

    :expectedresults: compute resource is added and removed from the location
    """
    url = LIBVIRT_RESOURCE_URL % settings.libvirt.libvirt_hostname
    resource = target_sat.api.LibvirtComputeResource(url=url).create()
    resource_name = resource.name + ' (Libvirt)'
    loc = target_sat.api.Location().create()
    with session:
        session.location.update(loc.name, {'compute_resources.resources.assigned': [resource_name]})
        loc_values = session.location.read(loc.name)
        assert loc_values['compute_resources']['resources']['assigned'][0] == resource_name
        session.location.update(
            loc.name, {'compute_resources.resources.unassigned': [resource_name]}
        )
        loc_values = session.location.read(loc.name)
        assert len(loc_values['compute_resources']['resources']['assigned']) == 0
        assert resource_name in loc_values['compute_resources']['resources']['unassigned']
