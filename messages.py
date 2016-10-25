class Call(object):
    LIST_CONTAINERS = 0
    LAUNCH_NESTED_CONTAINER_SESSION = 1
    ATTACH_CONTAINER_INPUT_STREAM = 2
    ATTACH_CONTAINER_OUTPUT_STREAM = 3

    def __init__(self, type, msg):
        self.type = type
        self.msg = msg

class ListContainersRequest(object):
    def __init__(self):
        pass

class ListContainersResponse(object):
    def __init__(self, container_ids):
        self.container_ids = container_ids

class LaunchNestedContainerSession(object):
    def __init__(self, container_id, cmd, args):
        self.container_id = container_id
        self.cmd = cmd
        self.args = args

class AttachContainerMessage(object):
    CONTROL_MSG = 0;
    IO_MSG = 1;

    def __init__(self, type, msg):
        self.type = type
        self.msg = msg

class ControlMsg(object):
    INITIATE_STREAM = 0
    WINDOW_SIZE = 1

    def __init__(self, type, msg):
        self.type = type
        self.msg = msg

class InitiateStream(object):
    def __init__(self, container_id, tty, interactive):
        self.container_id = container_id
        self.tty = tty
        self.interactive = interactive

class WindowSize(object):
    def __init__(self, rows, columns):
        self.rows = rows
        self.columns = columns

class TtyInfo(object):
    def __init__(self, window_size):
        self.window_size = window_size

class IOMsg(object):
    STDIN = 0
    STDOUT = 1
    STDERR = 2

    def __init__(self, type, data):
        self.type = type
        self.data = data
