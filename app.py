from contextlib import closing
import ntplib
from queue import Queue, Empty
import socket
import tkinter as tk
import threading


NTP_PORT = 123
SOCKET_TIMEOUT = 10

PORT_NUMBER = 0
PORT_STATUS = 1
PORT_HOST = 2

STATUS_SUCCESS = 'success'
STATUS_RUNNING = 'running'
STATUS_FINISHED = 'finished'

REQUIRED_PORTS = (
    (22,    'Support',                    '127.0.0.1'),
    (80,    'Web server',                 '127.0.0.1'),
    (123,   'Clock synchronization',      '127.0.0.1'),
    (443,   'Secure web server',          '127.0.0.1'),
    (3022,  'lol testing',                '127.0.0.1'),
    (5831,  'TCP portapt',                '127.0.0.1'),
    (5832,  'TCP portapt',                '127.0.0.1'),
    (11371, 'Secure verification server', '127.0.0.1'),
    (31767, 'Monitoring',                 '127.0.0.1'),
    (42873, 'Content synchronization',    '127.0.0.1'),
)


class Application():
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Liquid Galaxy Network Diagnostics Tool')
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.status_widgets = {}
        self.create_widgets()
        self.checker = None
        self.queue = Queue()
        self.root.call(
            'wm',
            'iconphoto',
            self.root._w,
            tk.Image('photo', file='logo-small.png')
        )

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
        self.report_frame = tk.Frame(self.root)

        # End Point logo
        logo = tk.PhotoImage(file='logo-large.png')
        label = tk.Label(
            self.root,
            image=logo
        )
        label.image = logo
        label.pack()

        # button_frame widgets
        self.do_checks_button = tk.Button(self.button_frame, text='Run diagnostics', command=self.do_checks)
        self.do_checks_button.grid(row=0, column=1)

        self.cancel_button = tk.Button(
            self.button_frame,
            text='Cancel',
            command=self.cancel,
        )
        self.cancel_button.grid(row=0, column=2)
        self.cancel_button.grid_remove()

        # status_frame widgets
        tk.Label(
            self.status_frame,
            text='Description',
            width=30,
            anchor='w',
        ).grid(row=0, column=0, sticky='nesw')
        tk.Label(
            self.status_frame,
            text='Status',
            width=8,
            anchor='w',
        ).grid(row=0, column=1, sticky='nesw')
        r = 1
        for port, description, host in REQUIRED_PORTS:
            tk.Label(
                self.status_frame,
                text=description,
                anchor='w',
            ).grid(row=r, column=0, sticky='nesw')

            status = tk.Label(
                self.status_frame,
                bg='grey',
                relief=tk.FLAT,
                width=60,
                height=2,
                wraplength=400,
            )
            status.grid(row=r, column=1, pady=(1,0))
            self.status_widgets[port] = status
            r += 1

        self.copy_button = tk.Button(
            self.report_frame,
            text='Copy to clipboard',
            command=self.copy_to_clipboard,
        )
        self.report_box = tk.Text(
            self.report_frame,
            state=tk.DISABLED,
        )

        # Pack frames
        self.button_frame.pack(fill='x')
        self.status_frame.pack(fill='x')
        self.report_frame.pack(fill='x')

        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_frame.grid_columnconfigure(1, weight=1)

    def copy_to_clipboard(self):
        self.root.clipboard_append(self.report_box.get('1.0', tk.END))
        self.root.update()

    def do_checks(self):
        if self.checker is not None: return
        self.do_checks_button.config(state=tk.DISABLED)
        for status in self.status_widgets.values():
            status.config(bg='grey')
        self.checker = PortChecker(self.queue, daemon=True)
        self.checker.start()
        self.cancel_button.grid()
        self.root.after(100, self.check_for_updates)
        if self.report_box is not None:
            self.report_box.config(state=tk.NORMAL)
            self.report_box.delete('1.0', tk.END)
            self.report_box.config(state=tk.DISABLED)

    def check_for_updates(self):
        try:
            p = self.queue.get(0)

            if p[PORT_STATUS] is STATUS_FINISHED:
                report = self.checker.report
                self.checker = None
                self.do_checks_button.config(state=tk.NORMAL)
                self.cancel_button.config(state=tk.NORMAL)
                self.cancel_button.grid_remove()
                self.report_box.config(state=tk.NORMAL)
                self.report_box.insert(tk.END, report)
                self.report_box.config(state=tk.DISABLED)
                self.report_box.pack()
                self.copy_button.pack(side=tk.RIGHT)
                return

            widget = self.status_widgets.get(p[PORT_NUMBER])

            if p[PORT_STATUS] is STATUS_RUNNING:
                widget.config(text='Checking port...')
            elif p[PORT_STATUS] is STATUS_SUCCESS:
                widget.config(text='Connection succeeded!',
                              bg = 'green')
            else:
                widget.config(text='Connection failed ({})'.format(p[PORT_STATUS]),
                              bg = 'red')
        except Empty:
            pass
        self.root.after(100, self.check_for_updates)


class PortChecker(threading.Thread):
    report = ""

    def __init__(self, queue, daemon=False):
        threading.Thread.__init__(self, daemon=daemon)
        self.queue = queue
        self.q = False

    def run(self):
        """
        Check that all ports in REQUIRED_PORTS are open.

        Return a list of tuples with the port number and a True or False value
        indicating whether or not it is open.
        """
        self.report = "Starting checks...\n"
        self.check_all_sockets()

    def quit(self):
        self.report += "Quitting!\n"
        self.q = True

    def check_all_sockets(self):
        for port, description, host in REQUIRED_PORTS:
            if self.q:
                break
            error = None
            self.report += "Checking connection to {}:{}... ".format(host, port)
            self.queue.put((
                port,
                STATUS_RUNNING
            ))
            if port == NTP_PORT:
                c = ntplib.NTPClient()
                try:
                    response = c.request(host, port)
                except Exception as e:
                    error = e
            else:
                error = self.check_socket(host, port)

            if error:
                self.report += "Connection failed. Error: {}\n".format(error)
                self.queue.put((
                    port,
                    error
                ))
            else:
                self.queue.put((
                    port,
                    STATUS_SUCCESS
                ))
                self.report += 'successful!\n'

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
