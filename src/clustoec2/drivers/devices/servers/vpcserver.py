#!/usr/bin/env python
#
# -*- mode:python; sh-basic-offset:4; indent-tabs-mode:nil; coding:utf-8 -*-
# vim:set tabstop=4 softtabstop=4 expandtab shiftwidth=4 fileencoding=utf-8:
#

import clusto
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

        if name:
            _name = name
        elif instance.tags.get('Name'):
            _name = instance.tags.get('Name')
        else:
            #TODO allocate a name dynamically and set the Name tag
            raise NotImplementedError

        # Instantiate
        cls(_name)

        # Get the instantiated instance
        # FIXME: likely not the way to do this...
        self = clusto.get_by_name(name)

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

        # FIXME: don't fail if subnet doesn't exist
        subnet = clusto.get_by_name(instance.subnet_id)
        if self not in subnet.contents():
            subnet.insert(self)

        # FIXME: don't fail if security group doesn't exist
        for sg in instance.groups:
            clusto_sg = clusto.get_by_name(sg.id)
            if self not in clusto_sg:
                clusto_sg.insert(self)

        os = instance.tags.get('Operating System')
        if os and os.lower() == 'centos':
            ver = instance.tags.get('Operating System Major Version')
            if ver:
                self.set_attr(key=u'system', subkey=u'centosversion', value=ver)

        return self
