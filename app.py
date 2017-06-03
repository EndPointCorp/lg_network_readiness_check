from contextlib import closing
import ntplib
from queue import Queue, Empty
import socket
import tkinter as tk
import threading


NTP_PORT = 123
SOCKET_TIMEOUT = 10
HOST = '127.0.0.1'
#HOST = '35.185.244.33'

PORT_NUMBER = 0
PORT_STATUS = 1

STATUS_SUCCESS = 'success'
STATUS_RUNNING = 'running'
STATUS_FINISHED = 'finished'

REQUIRED_PORTS = (
    (22, 'TCP ssh'),
    (80, 'TCP http'),
    (123, 'UDP ntp'),
    (443, 'TCP https'),
    (5831, 'TCP portapt'),
    (5832, 'TCP portapt'),
    (11371, 'PGP public key server'),
    (31767, 'TCP zabbix'),
    (42873, 'TCP rsync'),
)


class Application():
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("On-site diagnostics")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.status_widgets = {}
        self.create_widgets()
        self.checker = None
        self.queue = Queue()

    def on_close(self):
        self.cancel()
        self.root.destroy()

    def cancel(self):
        self.cancel_button.config(state=tk.DISABLED, text='Canceling...')
        if self.checker is not None:
            self.checker.quit()

    def create_widgets(self):
        # Initialize frames
        self.button_frame = tk.Frame(self.root)
        self.status_frame = tk.Frame(self.root)

        # button_frame widgets
        self.do_checks_button = tk.Button(self.button_frame, text='Check ports!', command=self.do_checks)
        self.do_checks_button.grid(row=0, column=1)

        self.cancel_button = tk.Button(
            self.button_frame,
            text='Cancel',
            command=self.cancel,
        )
        self.cancel_button.grid(row=0, column=2)
        self.cancel_button.grid_remove()

        self.host_entry_label = tk.Label(self.button_frame, text="Host: ")
        self.host_entry_label.grid(row=0, column=3)

        self.host_variable = tk.StringVar()
        self.host_entry = tk.Entry(self.button_frame, textvariable=self.host_variable)
        self.host_variable.set(HOST)
        self.host_entry.grid(row=0, column=4)

        # status_frame widgets
        tk.Label(
            self.status_frame,
            text='Port',
            width=6,
            anchor="w",
        ).grid(row=0, column=0, sticky="nesw")
        tk.Label(self.status_frame,
            text='Description',
            width=30,
            anchor="w",
        ).grid(row=0, column=1, sticky="nesw")
        tk.Label(
            self.status_frame,
            text='Status',
            width=8,
            anchor="w",
        ).grid(row=0, column=2, sticky="nesw")
        r = 1
        for port, description in REQUIRED_PORTS:
            tk.Label(
                self.status_frame,
                text=str(port),
                anchor="w",
            ).grid(row=r, column=0, sticky="nesw")
            tk.Label(
                self.status_frame,
                text=description,
                anchor="w",
            ).grid(row=r, column=1, sticky="nesw")
            status = tk.Label(
                self.status_frame,
                bg='grey',
                relief=tk.FLAT,
                width=60,
                height=2,
                wraplength=400,
            )
            status.grid(row=r, column=2, pady=(1,0))
            self.status_widgets[port] = status
            r += 1

        # Pack frames
        self.button_frame.pack(fill="x")
        self.status_frame.pack(fill="x")

        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_frame.grid_columnconfigure(1, weight=1)

    def do_checks(self):
        if self.checker is not None: return
        self.do_checks_button.config(state=tk.DISABLED)
        for status in self.status_widgets.values():
            status.config(bg='grey')
        self.checker = PortChecker(self.queue, daemon=True, host=self.host_variable.get())
        self.checker.start()
        self.cancel_button.grid()
        self.root.after(100, self.check_for_updates)

    def check_for_updates(self):
        try:
            p = self.queue.get(0)

            if p[PORT_STATUS] is STATUS_FINISHED:
                self.checker = None
                self.do_checks_button.config(state=tk.NORMAL)
                self.cancel_button.config(state=tk.NORMAL)
                self.cancel_button.grid_remove()
                return

            widget = self.status_widgets.get(p[PORT_NUMBER])

            if p[PORT_STATUS] is STATUS_RUNNING:
                widget.config(text='Checking port...')
            elif p[PORT_STATUS] is STATUS_SUCCESS:
                widget.config(text='Open!',
                              bg = 'green')
            else:
                widget.config(text='Port closed ({})'.format(p[PORT_STATUS]),
                              bg = 'red')
        except Empty:
            pass
        self.root.after(100, self.check_for_updates)


class PortChecker(threading.Thread):
    def __init__(self, queue, daemon=False, host=HOST):
        threading.Thread.__init__(self, daemon=daemon)
        self.host = host
        self.queue = queue
        self.q = False

    def run(self):
        """
        Check that all ports in REQUIRED_PORTS are open.

        Return a list of tuples with the port number and a True or False value
        indicating whether or not it is open.
        """
        self.check_all_sockets(self.host)

    def quit(self):
        print("quitting!")
        self.q = True

    def check_all_sockets(self, host):
        for port, description in REQUIRED_PORTS:
            if self.q:
                break
            error = None
            print("Checking port {}... ".format(port), end='', flush=True)
            self.queue.put((
                port,
                STATUS_RUNNING
            ))
            if port == NTP_PORT:
                c = ntplib.NTPClient()
                try:
                    response = c.request(host)
                except Exception as e:
                    error = e
            else:
                error = self.check_socket(host, port)

            if error:
                print("This port seems to be closed. Error number: {}".format(error))
                self.queue.put((
                    port,
                    error
                ))
            else:
                self.queue.put((
                    port,
                    STATUS_SUCCESS
                ))
                print("open!")

        self.queue.put((0, STATUS_FINISHED))

    def check_socket(self, host, port):
        """
        Try to connect to host:port, returning None if successful or the error returned.
        """
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            try:
                value = sock.connect((host, port))
                return None
            except Exception as e:
                return e


app = Application()

app.root.mainloop()
