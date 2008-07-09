#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free  Software Foundation; either version 2 of the License, or
# (at your option)  any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301 USA.
#

VM_TYPE_PV = 0
VM_TYPE_HVM = 1

class vm(object):
    """
    Generic configuration for a particular VM instance.

    At export, a plugin is guaranteed to have the at least the following
    values set (any others needed should be checked for, raising
    ValueError on failure):

    vm.name
    vm.description (defaults to empty string)
    vm.nr_vcpus (defaults to 1)
    vm.type
    vm.arch

    If vm.memory is set, it is in Mb units.
    """

    name = None
    suffix = None

    def __init__(self):
        self.name = None
        self.description = None
        self.memory = None
        self.nr_vcpus = None
        self.disks = [ ]
        self.type = VM_TYPE_HVM
        self.arch = "i686"

    def validate(self):
        """
        Validate all parameters, and fix up any unset values to meet the
        guarantees we make above.
        """

        if not self.name:
            raise ValueError("VM name is not set")
        if not self.description:
            self.description = ""
        if not self.nr_vcpus:
            self.nr_vcpus = 1
        if not self.type:
            raise ValueError("VM type is not set")
        if not self.arch:
            raise ValueError("VM arch is not set")
