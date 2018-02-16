#!/usr/bin/env python
#
# -*- mode:python; sh-basic-offset:4; indent-tabs-mode:nil; coding:utf-8 -*-
# vim:set tabstop=4 softtabstop=4 expandtab shiftwidth=4 fileencoding=utf-8:
#

import clusto
from uaext import EnvironmentPool
from clustoec2.drivers.locations.zones.subnet import VPCSubnet
from clustoec2.drivers.categories.securitygroup import  EC2SecurityGroup
from clustoec2.drivers.base import VPCMixin
from clustoec2.drivers.devices.servers import ec2server


class VPCVirtualServer(ec2server.EC2VirtualServer, VPCMixin):

    _driver_name = 'vpcvirtualserver'

    _instance = property(lambda self: self._get_instance())
    state = property(lambda self: self._get_instance_state())
    private_ips = property(lambda self: self.get_private_ips())

    @classmethod
    def register(cls, instance_id, name=None):
        """Return constructed instance based on AWS discovered attributes.

        Registers an already created AWS instance with clusto.  All
        expected clusto attributes and the needed pools for the instance
        are set on the returned instance.

        Arguments:
        instance_id -- AWS EC2 instance ID

        Keyword Arguments:
        name -- Name to create the instantiated EC2VirtualServer with
                (Defaults to the AWS tag 'Name', and if that is not found
                allocates a new unique eXXX stype name)
        """
        # Get the already created vpcconnman
        # FIXME: likely not the 'clusto way'
        vpcconnman = clusto.get_by_name('vpcconnman')
        conn = vpcconnman._connection()

        # Will fail with a 404 if instance_id is not found
        reservations = conn.get_all_instances([instance_id])
        instances = reservations[0].instances

        if len(reservations) > 1 or len(reservations[0].instances) > 1:
            raise ValueError("Instance ID '{}' not unique".format(instance_id))

        instance = reservations[0].instances[0]

        subnet = clusto.get_or_create(instance.subnet_id, VPCSubnet)
        clusto_sg = [clusto.get_or_create(sg.id, EC2SecurityGroup) for sg in instance.groups]

        env_tag = instance.tags.get('Environment')
        environment = None
        if env_tag:
            environment = clusto.get_by_name(env_tag, EnvironmentPool)

        # Instantiate
        if name:
            cls(name)
            self = clusto.get_by_name(name)
            if instance.tags.get('Name') is None:
                instance.add_tag('Name', name)
        elif instance.tags.get('Name'):
            cls(instance.tags.get('Name'))
            self = clusto.get_by_name(instance.tags.get('Name'))
        else:
            self = clusto.get_by_name('ec2-names').allocate(cls)
            if instance.tags.get('Name') is None:
                instance.add_tag('Name', self.name)

        if not vpcconnman.resources(self):
            vpcconnman.allocate(self)

        self._i = instance
        self.set_attr(key=u'aws', subkey=u'ec2_instance_type',
                      value=instance.instance_type)

        res = self._mgr_driver.resources(self)[0]
        mgr = self._mgr_driver.get_resource_manager(res)
        mgr.additional_attrs(self, resource={'instance': self._i},
                             number=res.number)
        self.update_metadata()
        self.reconcile_ebs_volumes()

        chef_role = instance.tags.get('Chef Role')
        if chef_role:
            self.set_attr(key=u'chef', subkey=u'role', value=chef_role)

        if self not in subnet.contents():
            subnet.insert(self)

        for sg in clusto_sg:
            if self not in sg.contents():
                sg.insert(self)

        if environment and self not in environment.contents():
            environment.insert(self)

        os = instance.tags.get('Operating System')
        if os and os.lower() == 'centos':
            ver = instance.tags.get('Operating System Major Version')
            if ver:
                self.set_attr(key=u'system', subkey=u'centosversion', value=ver)

        return self
