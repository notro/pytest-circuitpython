#!/usr/bin/env python3
#
# This file is part of the MicroPython project, http://micropython.org/
#
# The MIT License (MIT)
#
# Copyright (c) 2017 Scott Shawcroft for Adafruit Industries
# Copyright (c) 2018 Noralf Trønnes
#
# Parts taken from pyboard.py:
# Copyright (c) 2014-2016 Damien P. George
# Copyright (c) 2017 Paul Sokolovsky
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import collections
import errno
import functools
import inspect
import os
import re
import serial
import stat
import sys
import time
import types

import serial.tools.list_ports
import sh
import shutil

class CPboardError(BaseException):
    def __init__(self, *args, session=None):
        super().__init__(*args)
        self.session = session

class CPboardRemoteError(CPboardError):
    def __init__(self, error, session=None):
        super().__init__(error, session=session)
        self.error = error
        self.exc_name = None
        self.exc_val = None
        self.exc = None
        self.tb = None
        self.parse_traceback(error)

    def parse_traceback(self, error):
        if isinstance(error, bytes):
            error = error.decode('utf-8', errors='replace')

        lines = error.splitlines()
        if len(lines) < 3 or lines[0] != 'Traceback (most recent call last):':
            return

        tb = []
        for line in lines[1:-1]:
            m = re.match(r' +File "(.+)", line (\d+)(, in (.+))?', line)
            if not m:
                return
            tb.append((m.group(1), int(m.group(2)), m.group(4)))

        exc_name, sep, exc_val = lines[-1].partition(':')
        if not sep:
            return

        exc_val = exc_val.strip()
        self.exc_name = exc_name
        self.exc_val = exc_val

        try:
            exc_type = eval(exc_name)
        except:
            return

        if exc_val:
            exc = exc_type(exc_val)
        else:
            exc = exc_type()

        self.exc = exc
        self.tb = tb

    def create_traceback(self, func=None, tb=None):
        if func:
            for entry in self.tb:
                filename = os.path.basename(func.__code__.co_filename)
                if (entry[0] == filename or entry[0] == '<stdin>') and entry[2] == func.__name__:
                    # Make sure the lineno is not outside the function, ie. the caller
                    tb = [(filename, entry[1], entry[2])]
                    break
        if not tb:
            tb = self.tb
        if not tb:
            return

        # Source: https://gist.github.com/rusek/83d774fa40b257126c77
        prev_var = '_e'
        globs = {prev_var: ZeroDivisionError}
        for i, (filename, lineno, name) in enumerate(reversed(tb)):
            this_var = '_%d' % i

            if func:
                firstlineno = func.__code__.co_firstlineno
                source = '%sdef %s():%s raise %s()' % ('\n' * (firstlineno - 1), this_var, '\n' * (lineno - 1), prev_var)
            else:
                source = '%sdef %s(): raise %s()' % ('\n' * (lineno - 1), this_var, prev_var)

            eval(compile(source, filename, 'exec'), globs)

            prev_var = this_var
            func = globs[this_var]
            code = func.__code__
            func.__code__ = types.CodeType(
                code.co_argcount, code.co_kwonlyargcount, code.co_nlocals, code.co_stacksize, code.co_flags, code.co_code,
                code.co_consts, code.co_names, code.co_varnames, code.co_filename, name, code.co_firstlineno,
                code.co_lnotab, code.co_freevars, code.co_cellvars,
            )
        try:
            globs[prev_var]()
        except ZeroDivisionError:
            globs.clear()
            return sys.exc_info()[2].tb_next


# supervisor/messages/default.h:
MSG_NEWLINE = b"\r\n"
MSG_SAFE_MODE_CRASH = b"Looks like our core CircuitPython code crashed hard. Whoops!"
MSG_SAFE_MODE_BROWN_OUT_LINE_1 = b"The microcontroller's power dipped. Please make sure your power supply provides"
MSG_SAFE_MODE_BROWN_OUT_LINE_2 = b"enough power for the whole circuit and press reset (after ejecting CIRCUITPY)."
MSG_WAIT_BEFORE_REPL = b"Press any key to enter the REPL. Use CTRL-D to reload."

class REPL:
    CHAR_CTRL_A = b'\x01'
    CHAR_CTRL_B = b'\x02'
    CHAR_CTRL_C = b'\x03'
    CHAR_CTRL_D = b'\x04'

    def __init__(self, board):
        self.board = board
        self.write_chunk_size = 32
        self.safe_mode = False
        self.session = b''

    def __enter__(self):
        self.reset()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        pass

    @property
    def serial(self):
        return self.board.serial

    def read(self):
        try:
            if self.serial.inWaiting():
                data = self.serial.read(self.serial.inWaiting())
            else:
                data = b''
        except OSError as e:
            raise CPboardError('read error', session=self.session) from e
        self.session += data
        return data

    def read_until(self, ending, timeout=10, out=None):
        data = b''
        timeout_count = 0
        while True:
            if data.endswith(ending):
                break
            try:
                if self.serial.inWaiting() > 0:
                    new_data = self.serial.read(1)
                    data += new_data
                    self.session += new_data
                    if out:
                        out.write(str(new_data, encoding='utf8', errors='replace'))
                    timeout_count = 0
                else:
                    timeout_count += 1
                    if timeout is not None and timeout_count >= 100 * timeout:
                        raise TimeoutError(110, "timeout waiting for", ending)
                    time.sleep(0.01)
            except OSError as e:
                raise CPboardError('read error', session=self.session) from e
        return data

    def write(self, data, chunk_size=None):
        if chunk_size is None:
            chunk_size = self.write_chunk_size
        if not isinstance(data, bytes):
            data = bytes(data, encoding='utf8')

        for i in range(0, len(data), chunk_size):
            chunk = data[i:min(i + chunk_size, len(data))]
            self.session += chunk
            try:
                self.serial.write(chunk)
            except OSError as e:
                raise CPboardError('write error', session=self.session) from e
            time.sleep(0.01)

    def reset(self):
        # Use read() since serial.reset_input_buffer() fails with termios.error now and then
        self.read()
        self.session = b''
        self.write(b'\r' + REPL.CHAR_CTRL_C + REPL.CHAR_CTRL_C) # interrupt any running program
        self.write(b'\r' + REPL.CHAR_CTRL_B) # enter or reset friendly repl
        data = self.read_until(b'>>> ')

    def execute(self, code, timeout=10, async=False, out=None):
        self.read() # Throw away

        self.write(REPL.CHAR_CTRL_A)
        self.read_until(b'\r\n>')

        self.write(code)

        self.write(REPL.CHAR_CTRL_D)
        if async:
            return b'', b''
        self.read_until(b'OK')

        output = self.read_until(b'\x04', timeout=timeout, out=out)
        output = output[:-1]

        error = self.read_until(b'\x04')
        error = error[:-1]

        return output, error

    def run(self):
        if self.safe_mode:
            raise CPboardError("Can't run in safe mode", session=self.session)

        self.reset()

        self.write(REPL.CHAR_CTRL_D)
        data = self.read_until(b' output:\r\n')
        if b'Running in safe mode' in data:
            self.safe_mode = True
            raise CPboardError("Can't run in safe mode", session=self.session)

        # TODO: MSG_SAFE_MODE_CRASH
        # TODO: BROWNOUT

        marker = MSG_NEWLINE + MSG_WAIT_BEFORE_REPL + MSG_NEWLINE
        data = self.read_until(marker)
        data = data.split(marker)[0]

        # Haven't found out why we have to strip off this...
        if data.endswith(b'\r\n\r\n'):
            data = data[:-4]
        return data


class Disk:
    def __init__(self, dev):
        self.dev = os.path.realpath(dev)
        self.mountpoint = None
        with open('/etc/mtab', 'r') as f:
            mtab = f.read()
        mount = [mount.split(' ') for mount in mtab.splitlines() if mount.startswith(self.dev)]
        if mount:
            self._path = mount[0][1]
        else:
            name = os.path.basename(dev)
            sh.pmount("-tvfat", dev, name, _timeout=10)
            self.mountpoint = "/media/" + name
            self._path = self.mountpoint

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        try:
            self.close()
        except:
            pass

    @property
    def path(self):
        return self._path

    def close(self):
        if not self.mountpoint:
            return
        mountpoint = self.mountpoint
        self.mountpoint = None

        start_time = time.monotonic()
        unmounted = False
        while not unmounted and start_time - time.monotonic() < 30:
            try:
                sh.pumount(mountpoint)
                unmounted = True
            except sh.ErrorReturnCode_5:
                time.sleep(0.1)

    def sync(self):
        disk_device = os.path.basename(self.dev)[:-1]
        os.sync()
        # Monitor the block device so we know when the sync request is actually finished.
        with open("/sys/block/" + disk_device + "/stat", "r") as f:
            disk_inflight = 1
            last_wait_time = 0
            wait_time = 1
            while disk_inflight > 0 or wait_time > last_wait_time:
                f.seek(0)
                stats = f.read()
                block_stats = stats.split()
                disk_inflight = int(block_stats[8])
                last_wait_time = wait_time
                wait_time = int(block_stats[9])

    def copy(self, src, dst=None, sync=True):
        if dst is None:
            dst = os.path.basename(src)
        shutil.copy(src, os.path.join(self.path, dst))
        if sync:
            self.sync()


class ReplDisk(Disk):
    def __init__(self, board):
        self.board = board
        self._path = None
        self.curdir = '.'

    def close(self):
        pass

    def sync(self):
        pass

    def _command(self, command):
        #print('_command', command)
        self.board.exec(command, out=sys.stdout, reset_repl=False, raise_remote=True)

    def _eval(self, command):
        #print('_eval', command)
        return self.board.eval(command, reset_repl=False, raise_remote=True)

    def _os(self, do):
        return self._eval('__import__("os").%s' % do)

    def copy(self, src, dst, sync=True, force=False):
        #print('copy(%r, %r)' % (src, dst))

        if not force and self.exists(dst) and os.stat(src).st_size  == self.stat(dst).st_size:
            return False

        with open(src, 'rb') as f:
            self._command('f = open("%s", "wb");chunk = None' % dst)
            for chunk in iter(lambda: f.read(128), b''):
                #print(repr(chunk))
                self._command('chunk = %r' % chunk)
                self._command('f.write(chunk)')
            self._command('f.close();del f;del chunk')
        return True

    def stat(self, path):
        st = self._os('stat(%r)' % path)
        if isinstance(st, tuple):
            st = os.stat_result(st)
        #print('stat(%r): %r' %(path, st))
        return st

    def exists(self, path):
        """Test whether a path exists.  Returns False for broken symbolic links"""
        try:
            self.stat(path)
        except OSError:
            return False
        return True

    def isdir(self, s):
        """Return true if the pathname refers to an existing directory."""
        try:
            st = self.stat(s)
        except OSError:
            return False
        return stat.S_ISDIR(st.st_mode)

    def mkdir(self, path, mode=0o777, *, dir_fd=None):
        self._command('__import__("os").mkdir(%r)' % path)

    def makedirs(self, name, mode=0o777, exist_ok=False):
        head, tail = os.path.split(name)
        if not tail:
            head, tail = os.path.split(head)
        if head and tail and not self.exists(head):
            try:
                self.makedirs(head, exist_ok=exist_ok)
            except FileExistsError:
                # Defeats race condition when another thread created the path
                pass
            cdir = self.curdir
            if isinstance(tail, bytes):
                cdir = bytes(curdir, 'ASCII')
            if tail == cdir:           # xxx/newdir/. exists if xxx/newdir exists
                return
        try:
            self.mkdir(name, mode)
        except OSError:
            # Cannot rely on checking for EEXIST, since the operating system
            # could give priority to other errors like EACCES or EROFS
            if not exist_ok or not self.isdir(name):
                raise





class Firmware:
    def __init__(self, board):
        self.board = board

    @property
    def disk(self):
        disks = self.board.get_disks()
        if len(disks) != 1:
            raise RuntimeError("Boot disk not found for: " + self.board.device)
        return Disk(disks[0])

    @property
    def info(self):
        with self.disk as disk:
            fname = os.path.join(disk.path, 'INFO_UF2.TXT')
            with open(fname, 'r') as f:
                info = f.read()
        lines = info.splitlines()
        res = {}
        res['header'] = lines[0]
        for line in lines[1:]:
            k, _, v = line.partition(':')
            res[k.replace(':', '')] = v.strip()
        return res

    def upload(self, fw):
        with open(fw, 'rb') as f:
            header = f.read(32)
        if header[0:4] != b'UF2\n':
            raise ValueError('Only UF2 files are supported')
        self.board.close()
        with self.disk as disk:
            disk.copy(fw, sync=False)


class CPboard:
    @classmethod
    def from_try_all(cls, name, **kwargs):
        try:
            return CPboard.from_build_name(name, **kwargs)
        except ValueError:
            pass

        vendor, _, product = name.partition(':')
        if vendor and product:
            return CPboard.from_usb(idVendor=int(vendor, 16), idProduct=int(product, 16), **kwargs)

        return CPboard(name, **kwargs)

    @classmethod
    def from_build_name(cls, name, **kwargs):
        boards = {
                    #'arduino_zero'
                    'circuitplayground_express' : (0x239a, 0x8019),
                    #'feather_m0_adalogger' : (0x239a, ),
                    #'feather_m0_basic' : (0x239a, ),
                    'feather_m0_express' : (0x239a, 0x8023),
                    #'feather_m0_rfm69' : (0x239a, ),
                    #'feather_m0_rfm9x' : (0x239a, ),
                    #'feather_m0_supersized' : (0x239a, ),
                    #'feather_m4_express' : (0x239a, ),
                    #'gemma_m0' : (0x239a, ),
                    #'itsybitsy_m0_express' : (0x239a, ),
                    #'itsybitsy_m4_express' : (0x239a, ),
                    'metro_m0_express' : (0x239a, 0x8014),
                    'metro_m4_express' : (0x239a, 0x8021),
                    #'metro_m4_express_revb' : (0x239a, ),
                    #'pirkey_m0' : (0x239a, ),
                    #'trinket_m0' : (0x239a, ),
                    #'trinket_m0_haxpress' : (0x239a, ),
                    #'ugame10'
             }

        try:
            vendor, product = boards[name]
        except KeyError:
            raise ValueError("Unknown build name: " + name)

        return CPboard.from_usb(idVendor=vendor, idProduct=product, **kwargs)

    @classmethod
    def from_build_name_bootloader(cls, name, **kwargs):
        boards = {
                    #'arduino_zero'
                    #'circuitplayground_express' : (0x239a, ),
                    #'feather_m0_adalogger' : (0x239a, ),
                    #'feather_m0_basic' : (0x239a, ),
                    'feather_m0_express' : (0x239a, 0x001b),
                    #'feather_m0_rfm69' : (0x239a, ),
                    #'feather_m0_rfm9x' : (0x239a, ),
                    #'feather_m0_supersized' : (0x239a, ),
                    #'feather_m4_express' : (0x239a, ),
                    #'gemma_m0' : (0x239a, ),
                    #'itsybitsy_m0_express' : (0x239a, ),
                    #'itsybitsy_m4_express' : (0x239a, ),
                    #'metro_m0_express' : (0x239a, 0x8014),
                    'metro_m4_express' : (0x239a, 0x0021),
                    #'metro_m4_express_revb' : (0x239a, ),
                    #'pirkey_m0' : (0x239a, ),
                    #'trinket_m0' : (0x239a, ),
                    #'trinket_m0_haxpress' : (0x239a, ),
                    #'ugame10'
             }

        try:
            vendor, product = boards[name]
        except KeyError:
            raise ValueError("Unknown build name: " + name)

        board = CPboard.from_usb(idVendor=vendor, idProduct=product, **kwargs)
        board.bootloader = True
        return board

    @classmethod
    def from_usb(cls, baudrate=115200, wait=0, timeout=10, **kwargs):
        import usb.core
        dev = usb.core.find(**kwargs)
        if not dev:
            s = "Can't find USB device: "
            args = []
            for x in kwargs.items():
                try:
                    args.append('%s=0x%x' % x)
                except:
                    args.append('%s = %s' % x)
            raise RuntimeError("Can't find USB device: " + ', '.join(args))
        return cls(dev, baudrate=baudrate, wait=wait, timeout=timeout)

    def __init__(self, device, baudrate=115200, wait=0, timeout=10):
        self.device = device
        self.usb_dev = None
        try:
            # Is it a usb.core.Device?
            portstr = ':' + '.'.join(map(str, device.port_numbers)) + ':'
        except:
            pass
        else:
            serials = [serial for serial in os.listdir("/dev/serial/by-path") if portstr in serial]
            if len(serials) != 1:
                raise OSError(errno.ENOENT, "Can't find excatly one matching usb serial device")
            self.device = os.path.realpath("/dev/serial/by-path/" + serials[0])
            self.usb_dev = device

        self.baudrate = baudrate
        self.wait = wait
        self.timeout = timeout
        self.mount = None
        self.serial = None
        self.bootloader = False
        self.repl = REPL(self)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()

    def open(self, baudrate=None, wait=None):
        if self.serial:
            return
        if baudrate is None:
            baudrate = self.baudrate
        if wait is None:
            wait = self.wait

        delayed = False
        for attempt in range(wait + 1):
            try:
                self.serial = serial.Serial(self.device, baudrate=self.baudrate, timeout=self.timeout, write_timeout=self.timeout, interCharTimeout=1)
                break
            except OSError:
                if wait == 0:
                    continue
                if attempt == 0:
                    sys.stdout.write('Waiting {} seconds for board '.format(wait))
                    delayed = True
            time.sleep(1)
            sys.stdout.write('.')
            sys.stdout.flush()
        else:
            if delayed:
                print('')
            raise CPboardError('failed to access ' + self.device)
        if delayed:
            print('')

    def close(self):
        if self.serial:
            self.serial.close()
            self.serial = None

    def exec(self, command, timeout=10, async=False, out=None, reset_repl=True, raise_remote=True):
        if reset_repl:
            self.repl.reset()
        output, error = self.repl.execute(command, timeout=timeout, async=async, out=out)
        if error:
            exc = CPboardRemoteError(error, session=self.repl.session)
            if exc.exc and raise_remote:
                raise exc.exc from exc
            else:
                raise exc
        return output

    def exec_func(self, func, *args, **kwargs):
        #__tracebackhide__ = True # Hide this from pytest traceback

        timeout = kwargs.pop('_timeout', 10)
        async = kwargs.pop('_async', False)
        out = kwargs.pop('_out', None)
        reset_repl = kwargs.pop('_reset_repl', True)
        raise_remote = kwargs.pop('_raise_remote', True)
        decorator_strip = kwargs.pop('_decorator_strip', None)
        #res_modifier = kwargs.pop('_res_modifier', None)

        debug = False

        arg_str = ', '.join(repr(arg) for arg in args)
        kwarg_str = ', '.join(['%s=%r' % (k, v) for k, v in kwargs.items()])
        if arg_str and kwarg_str:
            all_args = arg_str + ', ' + kwarg_str
        else:
            all_args = arg_str + kwarg_str

        source = inspect.getsource(func)

        #print('------------------------\n' + source + '------------------------')

        if decorator_strip and source.startswith('@'):
            s = []
            done = False
            for line in source.splitlines():
                if done:
                    pass
                elif re.match(decorator_strip, line):
                    line = ''
                    done = True
                elif line.startswith('@'):
                    line = ''
                s.append(line)
            source = '\n'.join(s)

        source += "\n\n"
        source += "res = %s(%s)\n" % (func.__name__, all_args)
        #if res_modifier:
        #    source += res_modifier + '\n'

        source += "print('BEGINMARKER>' + repr(res) + '<ENDMARKER')\n"

        if debug:
            print('------------------------------------------------------------------------')
            print(source)
            print('------------------------------------------------------------------------')

        output = self.exec(source, timeout=timeout, async=async, out=out, reset_repl=reset_repl, raise_remote=raise_remote)

        output = output.decode('utf-8', errors='replace')
        #print(output)
        if 'BEGINMARKER>' not in output or '<ENDMARKER' not in output:
            raise CPboardError('output is missing markers', output)
        output = output.split('BEGINMARKER>')[1].split('<ENDMARKER')[0]
        res = unpickle(output)
        return res

    def eval(self, expression, timeout=10, async=False, out=None, reset_repl=True, raise_remote=True, strict=True):
        command = 'print({}, end="")'.format(expression)
        output = self.exec(command, timeout=timeout, async=async, out=out, reset_repl=reset_repl, raise_remote=raise_remote)

        try:
            res = eval(str(output, encoding='utf8'))
        except Exception as e:
            if strict:
                raise CPboardError('failed to eval: %s' % output) from e
            output = output.decode('utf-8', errors='replace')
            res = unpickle(output)
        return res

    def _reset(self, mode='NORMAL'):
        self.exec("import microcontroller;microcontroller.on_next_reset(microcontroller.RunMode.%s)" % mode)
        try:
            self.exec("import microcontroller;microcontroller.reset()", async=True)
        except CPboardError:
            pass

    def reset(self, safe_mode=False, delay=5, wait=10):
        self._reset('SAFE_MODE' if safe_mode else 'NORMAL')
        self.close()
        time.sleep(delay)
        self.open(wait)
        time.sleep(delay)

    def reset_to_bootloader(self, repl=False):
        if repl:
            self._reset('BOOTLOADER')
            self.close()
        else:
            self.close()
            s = serial.Serial(self.device, 1200, write_timeout=4, timeout=4)
            s.close()

    def get_port_info(self):
        portinfo = None
        for port_iter in serial.tools.list_ports.comports():
            if port_iter.device == self.device:
                portinfo = port_iter
                break
        return portinfo

    @property
    def serial_number(self):
        try: # Permissions are needed to read the value
            return self.usb_dev.serial_number
        except:
            pass
        p = self.get_port_info()
        return p.serial_number if p else None

    def get_disks(self):
        if self.usb_dev:
            portstr = ':' + '.'.join(map(str, self.usb_dev.port_numbers)) + ':'
            return ["/dev/disk/by-path/" + disk for disk in os.listdir("/dev/disk/by-path") if portstr in disk]
        serial = self.serial_number
        if not serial:
            raise RuntimeError("Serial number not found for: " + self.device)
        return ["/dev/disk/by-id/" + disk for disk in os.listdir("/dev/disk/by-id") if serial in disk]

    @property
    def disk(self):
        disks = self.get_disks()

        part = [part for part in disks if 'part1' in part]
        if not part:
            raise RuntimeError("Disk not found for: " + self.device)

        return Disk(part[0])

    @property
    def firmware(self):
        return Firmware(self)

    def execfile_disk(self, filename):
        with self.disk as disk:
            disk.copy(filename, 'code.py')

        with self.repl as repl:
            output = repl.run()
        return output

    def execfile(self, filename, timeout=10):
        if os.environ.get('CPBOARD_EXEC_MODE') == 'disk':
            return self.execfile_disk(filename)
        else:
            with open(filename, 'rb') as f:
                pyfile = f.read()
            return self.exec(pyfile, timeout=timeout)


def unpickle_fixup_typename(typename, field_names):
    if typename == 'struct_time':
        return 'time.struct_time'
    if field_names == ['sysname', 'nodename', 'release', 'version', 'machine']:
        return 'posix.uname_result'
    if not typename:
        return 'anonymous'
    return typename

def unpickle(s):
    try:
        return eval(s)
    except:
        pass

    # fix: * -> +
    m = re.search(r'(.*)\((.+)\)', s)
    #print(m)
    if not m:
        return s

    typename = m.group(1)
    kv_pairs = re.findall(r'([^=]+)=([^=]+)(?:, |$)', m.group(2))
    if not kv_pairs:
        return s
    #print(kv_pairs)
    field_names = [kv[0] for kv in kv_pairs]
    #print(field_names)
    try:
        values = [eval(kv[1]) for kv in kv_pairs]
    except:
        return s
    #print(values)

    typename = unpickle_fixup_typename(typename, field_names)

    nameparts = typename.split('.')
    if len(nameparts) == 1:
        nt = collections.namedtuple(typename, field_names)
        return nt(*values)
    elif len(nameparts) == 2:
        try:
            m = __import__(nameparts[0])
        except ImportError:
            return s
        cls = m.__dict__.get(nameparts[1], None)
        try:
            return cls(tuple(values))
        except:
            return s
    return s


# Implement just enough to make tests/run-tests work
PyboardError = CPboardError

class Pyboard:
    def __init__(self, device, baudrate=115200, user='micro', password='python', wait=0, _pytest=False):
        self.board = CPboard.from_try_all(device, baudrate=baudrate, wait=wait)
        if not _pytest:
            with self.board.disk as disk:
                disk.copy('skip_if.py')

    def close(self):
        self.board.close()

    def enter_raw_repl(self):
        self.board.open()

    def execfile(self, filename):
        return self.board.execfile(filename)


def remote(func):
    """Decorator to mark a board function

    This decorator can be used to define a function that should run on the CircuitPython board.
    Returned objects are converted to local objects if possible.
    Exceptions are also raised locally if possible.

    Example:

        @cpboard.remote
        def roundtrip_number(i, add=0):
            return i + add

        board = cpboard.CPboard(...)
        board.open()
        8 == roundtrip_number(board, 5, add=3)

    Special keyword arguments that are not passed on to the wrapped function:
    _timeout: Passed on to REPL.execute, how long it should wait in seconds.
    _out: Catch output from REPL.execute. Example: _out=sys.stdout

    """
    @functools.wraps(func)
    def remote_func_wrapper(board, *args, **kwargs):
        __tracebackhide__ = True # Hide this from pytest traceback
        try:
            return board.exec_func(func, *args, _raise_remote=False, _decorator_strip=r'@cpboard\.remote:', **kwargs)
        except CPboardRemoteError as e:
            if e.exc:
                e.exc.__traceback__ = e.create_traceback(func=func)
                raise e.exc from None
            raise

    return remote_func_wrapper


@remote
def os_uname():
    import os
    return os.uname()

def print_verbose(cargs, *args, **kwargs):
    if cargs.verbose:
        print(*args, flush=True, **kwargs)

def upload(args):
    try:
        board = CPboard.from_build_name_bootloader(args.board)
        print_verbose(args, 'Board is already in the bootloader')
    except (ValueError, RuntimeError):
        board = CPboard.from_try_all(args.board)

    print_verbose(args, "Serial number :", board.serial_number)

    if not (args.quiet or board.bootloader):
        board.open()
        print('Current version:', os_uname(board).version, flush=True)

    if not board.bootloader:
        print_verbose(args, 'Reset to bootloader...', end='')
        board.reset_to_bootloader(repl=True) # Feather M0 Express doesn't respond to 1200 baud
        time.sleep(5)
        print_verbose(args, 'done')

    print_verbose(args, 'Bootloader:', board.firmware.info)

    print_verbose(args, 'Upload firmware...', end='')
    board.firmware.upload(args.firmware)
    print_verbose(args, 'done')

    print_verbose(args, 'Wait for board...', end='')
    time.sleep(5)
    print_verbose(args, 'done')

    if not args.quiet:
        if board.bootloader:
            board = CPboard.from_try_all(args.board)
        board.open(wait=10)
        print('New version:', os_uname(board).version, flush=True)

def print_error_exit(args, e):
    if args.debug:
        return False
    if not args.quiet:
        print(e, file=sys.stderr)
    sys.exit(1)

def main():
    import argparse
    cmd_parser = argparse.ArgumentParser(description='Circuit Python Board Tool')
    cmd_parser.add_argument('board', help='build_name, vid:pid or /dev/tty')
    cmd_parser.add_argument('-f', '--firmware', help='upload UF2 firmware file')
    cmd_parser.add_argument('-c', '--command', help='program passed in as string')
    cmd_parser.add_argument('--tty', action='store_true', help='print tty')
    cmd_parser.add_argument('--verbose', '-v', action='count', default=0, help='be verbose')
    cmd_parser.add_argument('-q', '--quiet', action='store_true', help='be quiet')
    cmd_parser.add_argument('--debug', action='store_true', help='raise exceptions')
    args = cmd_parser.parse_args()

    if args.quiet:
        args.verbose = 0
        args.debug = False

    if args.firmware:
        try:
            upload(args)
        except BaseException as e:
            if not print_error_exit(args, e):
                raise
        sys.exit(0)

    try:
        board = CPboard.from_try_all(args.board)
    except BaseException as e:
        if not print_error_exit(args, e):
            raise

    if args.verbose:
        exec_mode = os.environ.get('CPBOARD_EXEC_MODE')
        if exec_mode:
            print('CPBOARD_EXEC_MODE =', exec_mode)

    # Make sure we can open serial
    try:
        with board:
            pass
    except BaseException as e:
        if not print_error_exit(args, e):
            raise

    if args.tty:
        print(board.device)
    elif args.command:
        with board as b:
            print(b.eval(args.command))
    else:
        with board as b:
            print('Device: ', end='')
            if b.usb_dev:
                print('%04x:%04x on ' % (b.usb_dev.idVendor, b.usb_dev.idProduct), end='')
            print(b.device)
            print('Serial number:', b.serial_number)
            uname = os_uname(b)
            print('os.uname:')
            print('  sysname:', uname.sysname)
            print('  nodename:', uname.nodename)
            print('  release:', uname.release)
            print('  version:', uname.version)
            print('  machine:', uname.machine)

if __name__ == "__main__":
    main()
