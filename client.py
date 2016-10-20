#! /usr/bin/env python

import os
import pickle
import requests
import sys
import signal
import time

from functools import partial
from Queue import Queue
from threading import Thread

from docopt_wrapper import docopt

from messages import Call
from messages import ListContainersRequest
from messages import ListContainersResponse
from messages import LaunchNestedContainer
from messages import AttachContainerMessage
from messages import ControlMsg
from messages import InitiateStream
from messages import WindowSize
from messages import TtyInfo
from messages import IOMsg

USAGE = \
"""Streaming HTTP Client

Usage:
  client container exec [--tty] [--interactive] <container-id> <cmd> [<args>...]
  client container attach [--tty] [--interactive] <container-id>

Options:
  --tty           Allocate a tty on the server before
                  attaching to the container.
  --interactive   Connect the stdin of the client to
                  the stdin of the container.
"""

session = requests.Session()
input_queue = Queue()
output_queue = Queue()
exit_queue = Queue()


def input_thread():
    for chunk in iter(partial(os.read, sys.stdin.fileno(), 1024), ''):
        io_msg = IOMsg(
            IOMsg.STDIN,
            chunk)

        attach_container_msg = AttachContainerMessage(
            AttachContainerMessage.IO_MSG,
            io_msg)

        input_queue.put(pickle.dumps(attach_container_msg))

    # To signal EOF we send an IOMsg with 0 content.
    attach_container_msg.msg.data = ""
    input_queue.put(pickle.dumps(attach_container_msg))

def output_thread():
    while True:
        msg = pickle.loads(output_queue.get())

        if msg.type == IOMsg.STDOUT:
            sys.stdout.write(msg.data)
        elif msg.type == IOMsg.STDERR:
            sys.stderr.write(msg.data)

        output_queue.task_done()


def window_resize_handler(signum, frame):
    rows, columns = os.popen('stty size', 'r').read().split()

    window_msg = WindowSize(
        rows,
        columns)

    control_msg = ControlMsg(
        ControlMsg.WINDOW_SIZE,
        window_msg)

    attach_container_msg = AttachContainerMessage(
        AttachContainerMessage.CONTROL_MSG,
        control_msg)

    input_queue.put(pickle.dumps(attach_container_msg))


def list_containers():
    headers = {'content-type': 'application/x-protobuf'}

    list_containers_request = ListContainersRequest()

    call_msg = Call(
        Call.LIST_CONTAINERS,
        list_containers_request)

    pickled_msg = pickle.dumps(call_msg)

    request = requests.Request(
              'POST',
              'http://{addr}'.format(addr=addr),
              headers=headers,
              data=pickled_msg).prepare()

    response = session.send(request)

    list_containers_response = pickle.loads(response.content)
    return list_containers_response.container_ids


def launch_nested_container_session(addr, launch_nested_container_msg):
    headers = {'connection': 'keep-alive',
               'content-type': 'application/x-protobuf'}

    call_msg = Call(
        Call.LAUNCH_NESTED_CONTAINER_SESSION,
        launch_nested_container_msg)

    pickled_msg = pickle.dumps(call_msg)

    request = requests.Request(
              'POST',
              'http://{addr}'.format(addr=addr),
              headers=headers,
              data=pickled_msg).prepare()

    response = session.send(request, stream=True)

    if response.status_code != 200:
        raise Exception()


def attach_container_input_stream(addr, initiate_stream_msg):
    def request_generator():
        control_msg = ControlMsg(
            ControlMsg.INITIATE_STREAM,
            initiate_stream_msg)

        attach_container_msg = AttachContainerMessage(
            AttachContainerMessage.CONTROL_MSG,
            control_msg)

        yield pickle.dumps(attach_container_msg)

        while True:
            yield input_queue.get()


    headers = {'connection': 'keep-alive',
               'content-type': 'application/x-protobuf',
               'transfer-encoding': 'chunked'}

    request = requests.Request(
              'POST',
              'http://{addr}'.format(addr=addr),
              headers=headers,
              data=request_generator()).prepare()

    response = session.send(request, stream=True)

    if response.status_code != 200:
        raise Exception()


def attach_container_output_stream(addr, initiate_stream_msg):
    headers = {'content-type': 'application/x-protobuf'}

    control_msg = ControlMsg(
        ControlMsg.INITIATE_STREAM,
        initiate_stream_msg)

    attach_container_msg = AttachContainerMessage(
        AttachContainerMessage.CONTROL_MSG,
        control_msg)

    call_msg = Call(
        Call.ATTACH_CONTAINER_OUTPUT_STREAM,
        attach_container_msg)

    pickled_msg = pickle.dumps(call_msg)

    request = requests.Request(
              'POST',
              'http://{addr}'.format(addr=addr),
              headers=headers,
              data=pickled_msg).prepare()

    response = session.send(request, stream=True)

    for chunk in response.iter_content(chunk_size=None):
        msg = pickle.loads(chunk)

        if msg.type == AttachContainerMessage.IO_MSG:
            output_queue.put(pickle.dumps(msg.msg))

    output_queue.join() 
    exit_queue.put(None)


# Valid for both "exec" and "attach"
if __name__ == "__main__":
    addr = "localhost:8888"

    args = docopt(
        USAGE,
        argv=sys.argv[3:],
        options_first=True,
        programs=["client container exec",
                  "client container attach"])

    if sys.argv[2] == "exec":
        args["container"] = True
        args["exec"] = True
        args["attach"] = False

    if sys.argv[2] == "attach":
        args["container"] = True
        args["exec"] = False
        args["attach"] = True

    threads = []

    if (sys.argv[2] == "exec"):
        msg = LaunchNestedContainer(
            args["<container-id>"],
            args["<cmd>"],
            args["<args>"])

        threads.append(Thread(
            target=launch_nested_container_session,
            args=(addr, msg)))
        threads[-1].daemon = True
        threads[-1].start()        

        while args["<container-id>"] not in list_containers():
            time.sleep(0.1)


    initiate_stream_msg = InitiateStream(
        args["<container-id>"],
        args["--tty"],
        args["--interactive"])

    if (args["--tty"]):
       signal.signal(signal.SIGWINCH, window_resize_handler)

    if (args["--interactive"]):
        threads.append(Thread(target=input_thread))
        threads[-1].daemon = True
        threads[-1].start()

        threads.append(Thread(
            target=attach_container_input_stream,
            args=(addr, initiate_stream_msg)))
        threads[-1].daemon = True
        threads[-1].start()

    threads.append(Thread(
        target=attach_container_output_stream,
        args=(addr, initiate_stream_msg)))
    threads[-1].daemon = True
    threads[-1].start()

    threads.append(Thread(target=output_thread))
    threads[-1].daemon = True
    threads[-1].start()

    try:
        exit_queue.get(block=True, timeout=sys.maxint)
    except KeyboardInterrupt:
        pass
