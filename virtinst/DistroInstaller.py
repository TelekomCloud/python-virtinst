#
# Copyright 2006-2009  Red Hat, Inc.
# Daniel P. Berrange <berrange@redhat.com>
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

import logging
import os

import _util
import Installer
from VirtualDisk import VirtualDisk
from User import User
import OSDistro

from virtinst import _virtinst as _

def _is_url(url):
    """
    Check if passed string is a (psuedo) valid http, ftp, or nfs url.
    """
    return (url.startswith("http://") or url.startswith("ftp://") or \
            url.startswith("nfs:")) and not os.path.exists(url)

def _sanitize_url(url):
    """
    Do nothing for http or ftp, but make sure nfs is in the expected format
    """
    if url.startswith("nfs://"):
        # Convert RFC compliant NFS      nfs://server/path/to/distro
        # to what mount/anaconda expect  nfs:server:/path/to/distro
        # and carry the latter form around internally
        url = "nfs:" + url[6:]

        # If we need to add the : after the server
        index = url.find("/", 4)
        if index == -1:
            raise ValueError(_("Invalid NFS format: No path specified."))
        if url[index - 1] != ":":
            url = url[:index] + ":" + url[index:]

    return url

class DistroInstaller(Installer.Installer):
    def __init__(self, type = "xen", location = None, boot = None,
                 extraargs = None, os_type = None, conn = None):
        Installer.Installer.__init__(self, type, location, boot, extraargs,
                                 os_type, conn=conn)

        self.install = {
            "kernel" : "",
            "initrd" : "",
            "extraargs" : "",
        }

        # True == location is a filesystem path
        # False == location is a url
        self._location_is_path = True


    # DistroInstaller specific methods/overwrites

    def get_location(self):
        return self._location
    def set_location(self, val):
        """
        Valid values for location:
        1) it can be a local file (ex. boot.iso), directory (ex. distro tree)
           or physical device (ex. cdrom media)
        2) tuple of the form (poolname, volname) pointing to a file or device
           which will set location as that path
        3) http, ftp, or nfs path for an install tree
        """
        is_tuple = False
        validated = True
        self._location_is_path = True

        # Basic validation
        if type(val) is not str and (type(val) is not tuple and len(val) != 2):
            raise ValueError(_("Invalid 'location' type %s." % type(val)))

        if type(val) is tuple and len(val) == 2:
            logging.debug("DistroInstaller location is a (poolname, volname)"
                          " tuple")
            if not self.conn:
                raise ValueError(_("'conn' must be specified if 'location' is"
                                   " a storage tuple."))
            is_tuple = True

        elif _is_url(val):
            val = _sanitize_url(val)
            self._location_is_path = False
            logging.debug("DistroInstaller location is a network source.")

        elif os.path.exists(os.path.abspath(val)) \
             and (not self.conn or not _util.is_uri_remote(self.conn.getURI())):
            val = os.path.abspath(val)
            logging.debug("DistroInstaller location is a local "
                          "file/path: %s" % val)

        else:
            # Didn't determine anything about the location
            validated = False


        if is_tuple or (validated == False and self.conn and
                        _util.is_storage_capable(self.conn)):
            # If user passed a storage tuple, OR
            # We couldn't determine the location type and a storage capable
            #   connection was passed:
            # Pass the parameters off to VirtualDisk to validate, and pull
            # out the path
            stuple = (is_tuple and val) or None
            path = (not validated and val) or None

            try:
                d = VirtualDisk(path=path, device=VirtualDisk.DEVICE_CDROM,
                                conn=self.conn, volName=stuple)
                val = d.path
            except Exception, e:
                logging.debug(str(e))
                raise ValueError(_("Checking installer location failed: "
                                   "Could not find media '%s'." % str(val)))
        elif not validated:
            raise ValueError(_("Install media location must be an NFS, HTTP "
                               "or FTP network install source, or an existing "
                               "file/device"))

        if (not self._location_is_path and val.startswith("nfs:") and not
            User.current().has_priv(User.PRIV_NFS_MOUNT,
                                    (self.conn and self.conn.getURI()))):
            raise ValueError(_('Privilege is required for NFS installations'))

        self._location = val
    location = property(get_location, set_location)


    # Private helper methods

    def _prepare_cdrom(self, guest, distro, meter):
        if not self._location_is_path:
            # Xen needs a boot.iso if its a http://, ftp://, or nfs: url
            cdrom = OSDistro.acquireBootDisk(self.location,
                                             meter, guest.arch,
                                             scratchdir = self.scratchdir,
                                             distro = distro)
            self._tmpfiles.append(cdrom)

        self._install_disk = VirtualDisk(path=self.location,
                                         conn=guest.conn,
                                         device=VirtualDisk.DEVICE_CDROM,
                                         readOnly=True,
                                         transient=True)

    def _prepare_kernel_and_initrd(self, guest, distro, meter):
        if self.boot is not None:
            # Got a local kernel/initrd already
            self.install["kernel"] = self.boot["kernel"]
            self.install["initrd"] = self.boot["initrd"]
            if not self.extraargs is None:
                self.install["extraargs"] = self.extraargs
        else:
            # Need to fetch the kernel & initrd from a remote site, or
            # out of a loopback mounted disk image/device

            (kernelfn, initrdfn, args), os_type = OSDistro.acquireKernel(guest,
                self.location, meter, guest.arch, scratchdir=self.scratchdir,
                type=self.os_type, distro=distro)

            # Only set OS type if the user didn't explictly pass one
            if guest.os_type == None and os_type:
                guest.os_type = os_type

            self.install["kernel"] = kernelfn
            self.install["initrd"] = initrdfn
            self.install["extraargs"] = args

            self._tmpfiles.append(kernelfn)
            self._tmpfiles.append(initrdfn)

        # If they're installing off a local file/device, we map it
        # through to a virtual CD or disk
        if (self.location is not None and self._location_is_path
           and not os.path.isdir(self.location)):
            device = VirtualDisk.DEVICE_DISK
            if guest._lookup_osdict_key('pv_cdrom_install'):
                device = VirtualDisk.DEVICE_CDROM

            self._install_disk = VirtualDisk(conn=guest.conn,
                                             device=device,
                                             path=self.location,
                                             readOnly=True,
                                             transient=True)

    # General Installer methods

    def prepare(self, guest, meter, distro = None):
        self.cleanup()

        self.install = {
            "kernel" : "",
            "initrd" : "",
            "extraargs" : "",
        }

        if self.cdrom:
            if self.location:
                self._prepare_cdrom(guest, distro, meter)
            else:
                # Booting from a cdrom directly allocated to the guest
                pass
        else:
            self._prepare_kernel_and_initrd(guest, distro, meter)

    def get_install_xml(self, guest, isinstall):
        if isinstall:
            bootdev = "cdrom"
        else:
            bootdev = "hd"

        return self._get_osblob_helper(isinstall=isinstall, guest=guest,
                                       kernel=self.install, bootdev=bootdev)

    def detect_distro(self):
        try:
            dist_info = OSDistro.detectMediaDistro(location=self.location,
                                                   arch=self.arch)
        except:
            logging.exception("Error attempting to detect distro.")
            return (None, None)

        # Verify these are valid values
        dtype, dvariant = dist_info
        import osdict

        if dtype and osdict.OS_TYPES.has_key(dtype):
            if not (dvariant and
                    osdict.OS_TYPES[dtype]["variants"].has_key(dvariant)):
                logging.debug("Variant returned from detect_distro is not "
                              "valid: %s" % dvariant)
                dvariant = None
        else:
            logging.debug("Type returned from detect_distro is not valid: %s"
                          % dtype)
            dtype = None
            dvariant = None

        return (dtype, dvariant)
