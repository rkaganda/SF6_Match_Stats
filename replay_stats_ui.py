import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk
import threading
import queue

import replay_stats


class MatchStatsUI:
    def __init__(self, master):
        self.master = master

        # update_plots thread
        self.thread = None
        
        # update_plots status queue
        self.status_queue = queue.Queue()

        # update_plots flag
        self.keep_running = threading.Event()
        self.keep_running.set()

        # notebook for images
        self.notebook = None
        
        master.title("Replay Stats")

        # SF6 Path Label, Entry, Dialog Button
        self.sf6_label = ttk.Label(master, text="SF6 Path:")
        self.sf6_label.grid(row=0, column=0, padx=10, pady=10, sticky='w')

        self.sf6_entry = ttk.Entry(master, width=50)
        self.sf6_entry.grid(row=0, column=1, padx=10, pady=5, sticky='w')

        self.sf6_button = ttk.Button(master, text="...", command=self.browse_folder)
        self.sf6_button.grid(row=0, column=2, padx=10, pady=10, sticky='w')

        # Status Label
        self.status_label = ttk.Label(master, text="Stopped.", anchor='w')
        self.status_label.grid(row=1, column=1, padx=10, pady=10, sticky='w')

        # Start/Stop Button
        self.start_button = ttk.Button(master, text="Start", command=self.on_start)
        self.start_button.grid(row=2, column=0, columnspan=3, pady=20, padx=10, sticky='w')

        # New Window Button
        self.new_window_button = ttk.Button(master, text="View Recent Match Stats...", command=self.create_new_window)
        self.new_window_button.grid(row=2, column=2, columnspan=3, pady=20, padx=10, sticky='w')

        # update_plots status flag
        self.status_update = threading.Event()

        # bind to destroy on_close
        self.master.bind('<Destroy>', self.on_close)

    def add_notebook_ing(self, img_path, label):
        try:
            img = Image.open(img_path)
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=label)

            photo = ImageTk.PhotoImage(img)

            label = ttk.Label(frame, image=photo)
            label.image = photo  # Keep reference to avoid garbage collection
            label.pack(padx=10, pady=10)
        except FileNotFoundError:
            print(f"missing {img_path}")
            pass

    def create_new_window(self):
        new_window = tk.Toplevel(self.master)
        new_window.title("Match Plots")

        self.notebook = ttk.Notebook(new_window)

        for round_num in range(0, 4):
            for player_num in range(1, 3):
                image_path = f"stats_img/round{round_num}_player{player_num}_dmg.png"
                label = f"Round {round_num} Player {player_num} Damage"
                self.add_notebook_ing(image_path, label)
            image_path = f"stats_img/round{round_num}_drive.png"
            label = f"Round {int(round_num+1)} Drive Usage/Lost"
            self.add_notebook_ing(image_path, label)
        image_path = f'stats_img/match_stats.png'
        label = f"Match Statistics"
        self.add_notebook_ing(image_path, label)

        self.notebook.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:  # if folder was selected
            self.sf6_entry.delete(0, tk.END)  # clear entry
            self.sf6_entry.insert(0, folder_selected)  # update entry

    def on_start(self):
        # change the button to "Stop"
        self.start_button.config(text="Stop", command=self.on_stop)

        # start the update_plots function in a separate thread
        self.keep_running.set()
        self.thread = threading.Thread(target=self.update_plots, args=(self.sf6_entry.get(),))
        self.thread.start()

        # check for updates
        self.check_for_updates()

    def on_stop(self):
        # update status queue
        self.status_queue.put("Stopping...")
        self.status_update.set()

        # clear flag to stop update_plots
        self.keep_running.clear()

        # change the button back to "Start"
        self.start_button.config(text="Start", command=self.on_start)

        # update status queue
        self.status_queue.put("Stopped.")
        self.status_update.set()

    def on_close(self, event=None):
        # clear flag to stop update_plots
        self.keep_running.clear()

        # destroy main thread after wait
        self.master.after(100, self.master.destroy)

    def check_for_updates(self):
        # while the queue isn't empy
        while not self.status_queue.empty():
            # get the new status
            new_status = self.status_queue.get()
            # update label with new status
            self.status_label['text'] = new_status

        # schedule next check_for_updates
        self.master.after(100, self.check_for_updates)  # Check every 100ms

    def update_plots(self, s6_path):
        if replay_stats.replay_file_exists(filename=f"{s6_path}/reframework/data/{replay_stats.replay_name}"):
            # load recent replay file
            rounds_df, player_character = replay_stats.load_recent_file(s6_path)

            # update status
            self.status_queue.put("Updating Plots...")
            self.status_update.set()
            # write plots
            replay_stats.update_plots(rounds_df, player_character)
            # update status
            self.status_queue.put("Updated Plots.")
            self.status_update.set()

        # while flag is set
        while self.keep_running.is_set():
            # update status
            self.status_queue.put("Waiting for Match...")
            self.status_update.set()
            # wait for new match file
            replay_stats.watch_file_for_changes(filename=f"{s6_path}/reframework/data/{replay_stats.replay_name}")

            # update status
            self.status_queue.put("Updating Plots...")
            self.status_update.set()
            # write plots
            rounds_df, player_character = replay_stats.load_recent_file(s6_path)
            replay_stats.update_plots(rounds_df, player_character)

            # update status
            self.status_queue.put("Updated Plots.")
            self.status_update.set()


if __name__ == "__main__":
    root = tk.Tk()
    app = MatchStatsUI(root)
    root.mainloop()
