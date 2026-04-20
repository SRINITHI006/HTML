import tkinter as tk
from tkinter import ttk, filedialog
from multiprocessing import Process, Queue, Pipe, Manager, Lock
import multiprocessing
import time
import os

# global state (simple for now)
active_processes = []
shared_manager = None
shared_data = None
execution_start_time = None

def log_event(log_queue, level, message):
    """Push log messages into the queue with level tags."""
    log_queue.put(f"[{level}] {message}")

def queue_sender(queue, log_queue):
    pid = os.getpid()
    for i in range(3):
        time.sleep(1)
        msg = f"{pid}-{i}"
        queue.put(msg)
        log_event(log_queue, "INFO", f"SENDER {pid} -> {msg}")


def queue_receiver(queue, log_queue):
    pid = os.getpid()
    for _ in range(5):
        if not queue.empty():
            msg = queue.get()
            log_event(log_queue, "INFO", f"RECEIVER {pid} <- {msg}")
        time.sleep(1)


def pipe_sender(conn, log_queue):
    pid = os.getpid()
    for i in range(3):
        time.sleep(1)
        conn.send(f"{pid}-{i}")
        log_event(log_queue, "INFO", f"SENDER {pid} -> data")
    conn.close()


def pipe_receiver(conn, log_queue):
    pid = os.getpid()
    for _ in range(5):
        try:
            if conn.poll():
                msg = conn.recv()
                log_event(log_queue, "INFO", f"RECEIVER {pid} <- {msg}")
        except Exception:
            log_event(log_queue, "ERROR", "Pipe closed unexpectedly")
            break
        time.sleep(1)


def shared_memory_writer(shared, log_queue):
    pid = os.getpid()
    for i in range(3):
        time.sleep(1)
        shared['data'] = f"{pid}-{i}"
        log_event(log_queue, "INFO", f"WRITE {shared['data']}")


def shared_memory_reader(shared, log_queue):
    pid = os.getpid()
    for _ in range(5):
        time.sleep(1)
        if 'data' in shared:
            log_event(log_queue, "INFO", f"READ {shared['data']}")


def deadlock_task_one(lock_a, lock_b):
    with lock_a:
        time.sleep(1)
        with lock_b:
            pass


def deadlock_task_two(lock_a, lock_b):
    with lock_b:
        time.sleep(1)
        with lock_a:
            pass


class IPCDebuggerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IPC Debugger")
        self.root.geometry("900x700")
        self.root.configure(bg="#121212")

       
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass

        self.ipc_mode = tk.StringVar(value="Queue")
        self.log_queue = Queue()

        self.setup_ui()
        self.refresh_logs()


    def setup_ui(self):
        tk.Label(self.root, text="IPC Debugger",
                 font=("Segoe UI", 18, "bold"),
                 fg="#E0E0E0", bg="#121212").pack(pady=10)

        ttk.Combobox(self.root,
                     textvariable=self.ipc_mode,
                     values=["Queue", "Pipe", "Shared Memory"],
                     state="readonly").pack()

        btn_frame = tk.Frame(self.root, bg="#121212")
        btn_frame.pack(pady=10)

        button_style = {
            "bg": "#2C2C2C",
            "fg": "#E0E0E0",
            "bd": 0,
            "width": 12
        }

        tk.Button(btn_frame, text="Start", command=self.start_ipc, **button_style).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Deadlock", command=self.trigger_deadlock, **button_style).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Stop", command=self.stop_ipc, **button_style).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Export Logs", command=self.export_logs, **button_style).pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(self.root, text="Idle",
                                     fg="#B0BEC5", bg="#121212")
        self.status_label.pack()

        self.metrics_label = tk.Label(self.root, text="",
                                      fg="#B0BEC5", bg="#121212")
        self.metrics_label.pack()

        self.canvas = tk.Canvas(self.root, width=600, height=250, bg="#EAEAEA")
        self.canvas.pack(pady=10)

        self.log_box = tk.Text(self.root,
                               bg="#1E1E1E",
                               fg="#D0D0D0",
                               font=("Consolas", 10))
        self.log_box.pack(fill=tk.BOTH, expand=True)

    def draw_process_flow(self, mode):
        self.canvas.delete("all")

        self.canvas.create_oval(50, 100, 120, 170, outline="#555", width=2)
        self.canvas.create_text(85, 135, text="P1")

        self.canvas.create_oval(480, 100, 550, 170, outline="#555", width=2)
        self.canvas.create_text(515, 135, text="P2")

        self.canvas.create_line(120, 135, 480, 135, arrow=tk.LAST, width=2)

        self.canvas.create_text(300, 80, text=mode)

    def animate_transfer(self):
        dot = self.canvas.create_oval(120, 130, 135, 145, fill="#444")

        for _ in range(36):
            self.canvas.move(dot, 10, 0)
            self.root.update()
            time.sleep(0.03)


    def start_ipc(self):
        global shared_manager, shared_data, execution_start_time

        execution_start_time = time.time()
        self.status_label.config(text="Running")

        self.draw_process_flow(self.ipc_mode.get())

        if self.ipc_mode.get() == "Queue":
            q = Queue()
            p1 = Process(target=queue_sender, args=(q, self.log_queue))
            p2 = Process(target=queue_receiver, args=(q, self.log_queue))

        elif self.ipc_mode.get() == "Pipe":
            parent_conn, child_conn = Pipe()
            p1 = Process(target=pipe_sender, args=(parent_conn, self.log_queue))
            p2 = Process(target=pipe_receiver, args=(child_conn, self.log_queue))

        else:
            if shared_manager is None:
                shared_manager = Manager()
                shared_data = shared_manager.dict()

            p1 = Process(target=shared_memory_writer, args=(shared_data, self.log_queue))
            p2 = Process(target=shared_memory_reader, args=(shared_data, self.log_queue))

        active_processes.extend([p1, p2])
        p1.start()
        p2.start()

        self.root.after(500, self.animate_transfer)

    def trigger_deadlock(self):
        lock1, lock2 = Lock(), Lock()

        p1 = Process(target=deadlock_task_one, args=(lock1, lock2))
        p2 = Process(target=deadlock_task_two, args=(lock2, lock1))

        active_processes.extend([p1, p2])
        p1.start()
        p2.start()

        self.status_label.config(text="Deadlock Running")
        self.log_box.insert(tk.END, "[WARNING] Deadlock triggered\n")

    def stop_ipc(self):
        global execution_start_time

        for p in active_processes:
            if p.is_alive():
                p.terminate()
                p.join()

        active_processes.clear()
        self.status_label.config(text="Stopped")

        if execution_start_time:
            duration = round(time.time() - execution_start_time, 2)
            self.metrics_label.config(text=f"Execution Time: {duration}s")

    def export_logs(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt")
        if file_path:
            with open(file_path, "w") as f:
                f.write(self.log_box.get("1.0", tk.END))

    def refresh_logs(self):
        while not self.log_queue.empty():
            message = self.log_queue.get()
            self.log_box.insert(tk.END, message + "\n")
            self.log_box.see(tk.END)

        self.root.after(500, self.refresh_logs)

if __name__ == "__main__":
    multiprocessing.freeze_support()

    root = tk.Tk()
    app = IPCDebuggerApp(root)
    root.mainloop()