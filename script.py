import sys
import math
import random
import ctypes
from ctypes import wintypes
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtNetwork import QUdpSocket, QHostAddress

################################################################
# Low-level mouse hook (Windows only)
################################################################

WH_MOUSE_LL = 14
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class MouseHook:
    def __init__(self):
        self.hHook = None
        self._callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        self._hook_callback = None

    def start(self):
        """
        Install the low-level mouse hook to block user-generated mouse events.
        """
        if self.hHook is not None:
            return  # Already hooked

        WM_MOUSEMOVE = 0x0200

        def low_level_mouse_proc(nCode, wParam, lParam):
            """
            Callback for every user mouse event (including touchpad).
            We block movement events so the user can't move the mouse physically.
            """
            if nCode >= 0:
                if wParam == WM_MOUSEMOVE:
                    # Block all physical mouse moves
                    return 1  # Non-zero => swallow event
            return user32.CallNextHookEx(self.hHook, nCode, wParam, lParam)

        self._hook_callback = self._callback_type(low_level_mouse_proc)
        self.hHook = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._hook_callback,
            kernel32.GetModuleHandleW(None),
            0
        )

    def stop(self):
        """
        Uninstall the low-level mouse hook, restoring normal user mouse control.
        """
        if self.hHook is not None:
            user32.UnhookWindowsHookEx(self.hHook)
            self.hHook = None
            self._hook_callback = None


################################################################
# Merged DesktopSprite class
################################################################

class DesktopSprite(QtWidgets.QWidget):
    def __init__(self, sprite_path, paw_path):
        super().__init__()

        # 1) Make a top-level, borderless, transparent overlay
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # 2) Resize to fill the entire screen
        screen_geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geo)

        # Load main sprite
        self.sprite = QtGui.QPixmap(sprite_path)
        if self.sprite.isNull():
            print(f"[ERROR] Sprite image '{sprite_path}' failed to load.")
        else:
            print(f"[INFO] Sprite loaded: {sprite_path} ({self.sprite.width()}x{self.sprite.height()})")
            self.kiky_pixmap = self.sprite.scaled(
                250, 250,
                QtCore.Qt.IgnoreAspectRatio,
                # QtCore.Qt.SmoothTransformation
            )
            print("[INFO] Kiky resized to 250x250.")

        # Load paw sprite and resize to 50x50 px
        self.paw_pixmap = QtGui.QPixmap(paw_path)
        if self.paw_pixmap.isNull():
            print(f"[ERROR] Paw image '{paw_path}' failed to load.")
        else:
            print(f"[INFO] Paw loaded: {paw_path} ({self.paw_pixmap.width()}x{self.paw_pixmap.height()})")
            self.paw_pixmap = self.paw_pixmap.scaled(
                50, 50,
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            print("[INFO] Paw resized to 50x50.")

        # Load bubble sprite for the dialogue
        self.bubble_pixmap = QtGui.QPixmap("dialogue_window.svg")
        if self.bubble_pixmap.isNull():
            print("[WARNING] 'dialogue_window.svg' failed to load, using fallback painting.")
        else:
            print(f"[INFO] Dialogue bubble loaded: dialogue_window.svg "
                  f"({self.bubble_pixmap.width()}x{self.bubble_pixmap.height()})")

        # Sprite position and velocity
        self.sprite_x = 0
        self.sprite_y = 0
        self.vx = 0
        self.vy = 0

        # Movement parameters
        self.accel = 0.03
        self.friction = 0.75
        self.parallax_factor = 0.15

        # Paw-trace logic
        self.paw_traces = []
        self.fade_time = 2000  # Paw fade (ms)

        # Interval logic for generating paws
        self.base_paw_interval = 500
        self.min_paw_interval = 200
        self.spawn_rate_factor = 4.0
        self.last_paw_time = QtCore.QTime.currentTime().addMSecs(-self.base_paw_interval)
        self.paw_step_index = 0

        # ==============================
        # TIMERS (store original values)
        # ==============================
        self.original_update_interval_ms = 16
        self.original_dialog_min = 5
        self.original_dialog_max = 7
        self.original_hide_dialog_ms = 5000
        self.original_takeover_min = 30
        self.original_takeover_max = 180
        self.original_effect_duration_min = 10
        self.original_effect_duration_max = 15
        self.original_base_paw_interval = self.base_paw_interval
        self.original_min_paw_interval  = self.min_paw_interval

        # RAMPAGE
        self.rampage_mode = False
        self.dialog_factor = 1.0
        self.takeover_factor = 1.0
        self.min_factor = 0.1  # 10% minimum

        # For exit animation after rampage
        self.rampage_exit_running = False
        self.rampage_exit_start_time = None
        self.rampage_exit_duration = 1.5  # 1.5s to animate offscreen
        self.rampage_exit_start_pos = QtCore.QPoint(0, 0)
        self.rampage_exit_end_pos = QtCore.QPoint(0, 0)

        # --- 1) Timer: continuous update
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_sprite_position)
        self.timer.start(self.original_update_interval_ms)

        # --- 2) Timer: random takeover
        self.random_start_timer = QtCore.QTimer()
        self.random_start_timer.setSingleShot(True)
        self.random_start_timer.timeout.connect(self.start_cursor_takeover)

        # --- 3) Timer: move cursor around
        self.cursor_move_timer = QtCore.QTimer()
        self.cursor_move_timer.timeout.connect(self.move_cursor_around)
        self.cursor_move_start_time = None
        self.cursor_move_duration = 0
        self.from_pos = None
        self.to_pos = None

        # Mouse hook manager
        self.mouse_hook = MouseHook()

        # Initially, let's skip scheduling takeover if not in rampage
        self.schedule_next_cursor_takeover()

        # Track previous velocity
        self.prev_vx = 0
        self.prev_vy = 0

        # Dialog logic
        self.dialog_messages = [
            "Hope Santa will finally seat on a diet",
            "If two vegans are having a fight is it still considered a beef?",
            "Hungry? Eat the government!",
            "Do not have money? Have you ever tried tax evasion?",
            "I think that Кanye West is super overrated",
        ]
        self.dialog_visible = False
        self.dialog_text = ""
        self.dialog_timer = QtCore.QTimer()
        self.dialog_timer.setSingleShot(True)
        self.dialog_timer.timeout.connect(self.show_dialog_random)

        self.hide_dialog_timer = QtCore.QTimer()
        self.hide_dialog_timer.setSingleShot(True)
        self.hide_dialog_timer.timeout.connect(self.hide_dialog)

        # Start first random dialog schedule
        self.schedule_next_dialog()

        self.dialog_rect = QtCore.QRect()
        self.updateWindowMask()

        # RAMPAGE TRIGGER
        self.rampage_trigger_timer = QtCore.QTimer()
        self.rampage_trigger_timer.setSingleShot(True)
        self.rampage_trigger_timer.timeout.connect(self.rampage_on)
        self.rampage_trigger_timer.start(10_000)  # 60s

        # UDP
        self.udp_socket = QUdpSocket(self)
        self.udp_socket.bind(QHostAddress.Any, 12345)
        self.udp_socket.readyRead.connect(self.handle_broadcast)

        # NON-RAMPAGE RUN
        self.non_rampage_timer = QtCore.QTimer()
        self.non_rampage_timer.timeout.connect(self.trigger_non_rampage_run)
        self.non_rampage_timer.start(3_000)  # runs every 10s (example)

        self.non_rampage_running = False
        self.non_rampage_run_start_time = None
        self.non_rampage_start = QtCore.QPoint(0, 0)
        self.non_rampage_end = QtCore.QPoint(0, 0)
        self.non_rampage_duration = 5  # run across in ~5 sec

        # Track when we can trigger the next non-rampage run
        # (to ensure we don't interrupt an ongoing run)
        self.non_rampage_can_trigger_run = True

    ################################################################
    # RAMPAGE
    ################################################################
    def rampage_on(self):
        if self.rampage_mode:
            return
        self.rampage_mode = True
        print("[RAMPAGE] Rampage mode activated.")

        # Now that rampage is on, let's schedule a takeover & dialogs again
        self.schedule_next_cursor_takeover()
        self.schedule_next_dialog()

    def rampage_off(self):
        """
        1) Stop any mouse takeover or dialogs.
        2) Trigger an exit animation to move the sprite offscreen.
        3) Once the animation is finished, do finalize_rampage_off().
        """
        if not self.rampage_mode:
            return

        # Immediately stop any ongoing mouse takeover
        if getattr(self, "effect_active", False):
            self.stop_cursor_takeover()

        # Hide any visible dialog (and stop scheduling more dialogs)
        if self.dialog_visible:
            self.hide_dialog()
        self.dialog_timer.stop()
        self.hide_dialog_timer.stop()

        # Also stop next random takeover scheduling
        self.random_start_timer.stop()

        # Start the exit animation
        self.rampage_exit_running = True
        self.rampage_exit_start_time = QtCore.QTime.currentTime()
        self.rampage_exit_start_pos = QtCore.QPoint(int(self.sprite_x), int(self.sprite_y))
        self.rampage_exit_end_pos = self.pick_offscreen_point()  # random offscreen
        print(f"[RAMPAGE] Rampage ending. Exiting offscreen from {self.rampage_exit_start_pos} to {self.rampage_exit_end_pos}...")

    def finalize_rampage_off(self):
        """
        Final cleanup once exit animation is done.
        Resets rampage parameters and re-starts the rampage trigger timer.
        """
        self.rampage_mode = False
        self.dialog_factor = 1.0
        self.takeover_factor = 1.0
        self.rampage_exit_running = False
        print("[RAMPAGE] Rampage mode ended completely.")

        # Restart rampage trigger for next time
        self.rampage_trigger_timer.start(60_000)  # re-arm for 60s

    def handle_broadcast(self):
        while self.udp_socket.hasPendingDatagrams():
            data, host, port = self.udp_socket.readDatagram(self.udp_socket.pendingDatagramSize())
            message = data.decode("utf-8").strip()
            if message == "Gifts Collected!":
                print("[UDP] Received 'Gifts Collected!' => stopping rampage.")
                self.rampage_off()

    ################################################################
    # PAINT
    ################################################################
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        now = QtCore.QTime.currentTime()

        # Draw paw traces
        for paw in list(self.paw_traces):
            elapsed = paw['birth_time'].msecsTo(now)
            if elapsed > self.fade_time:
                self.paw_traces.remove(paw)
                continue

            alpha = 255 - int(255 * elapsed / self.fade_time)
            painter.save()
            painter.setOpacity(alpha / 255.0)
            painter.translate(paw['x'], paw['y'])
            painter.rotate(paw['angle'])
            painter.drawPixmap(-self.paw_pixmap.width() // 2,
                               -self.paw_pixmap.height() // 2,
                               self.paw_pixmap)
            painter.restore()

        # Draw main sprite
        painter.save()
        painter.drawPixmap(int(self.sprite_x),
                           int(self.sprite_y),
                           self.kiky_pixmap)
        painter.restore()

        # Draw bubble if visible (only if rampage_mode)
        if self.dialog_visible and self.rampage_mode and not self.kiky_pixmap.isNull():
            font = QtGui.QFont()
            font.setPointSize(12)
            painter.setFont(font)
            metrics = QtGui.QFontMetrics(font)

            text_margin = 20
            max_width = 350
            text_bounding_rect = metrics.boundingRect(
                0, 0, max_width, 0,
                QtCore.Qt.TextWordWrap,
                self.dialog_text
            )

            bubble_width = text_bounding_rect.width() + 2 * text_margin
            bubble_height = text_bounding_rect.height() + 2 * text_margin

            tail_margin = max(20, int(0.35 * bubble_height))
            bubble_height += tail_margin

            if not self.bubble_pixmap.isNull():
                self.bubble_pixmap = self.bubble_pixmap.scaled(
                    bubble_width, bubble_height,
                    QtCore.Qt.KeepAspectRatioByExpanding,
                    QtCore.Qt.SmoothTransformation
                )

            bubble_x = int(self.sprite_x) - bubble_width - 30
            bubble_y = int(self.sprite_y)

            screen_geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
            if bubble_x < 0:
                bubble_x = 0
            if bubble_y + bubble_height > screen_geo.height():
                bubble_y = screen_geo.height() - bubble_height

            self.dialog_rect = QtCore.QRect(bubble_x, bubble_y, bubble_width, bubble_height)

            painter.save()
            painter.drawPixmap(bubble_x, bubble_y, self.bubble_pixmap)
            painter.restore()

            text_rect = QtCore.QRect(
                bubble_x + text_margin,
                bubble_y + text_margin,
                text_bounding_rect.width(),
                text_bounding_rect.height()
            )
            painter.save()
            painter.setPen(QtCore.Qt.black)
            painter.drawText(text_rect,
                             QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop | QtCore.Qt.TextWordWrap,
                             self.dialog_text)
            painter.restore()
        else:
            self.dialog_rect = QtCore.QRect()

    ################################################################
    # DIALOG LOGIC (only in rampage)
    ################################################################
    def schedule_next_dialog(self):
        if not self.rampage_mode:
            print("[INFO] Not in rampage mode => skipping dialog scheduling.")
            self.dialog_timer.stop()
            self.hide_dialog_timer.stop()
            return

        base_min = self.original_dialog_min
        base_max = self.original_dialog_max

        if self.rampage_mode:
            self.dialog_factor = max(self.min_factor, self.dialog_factor * 0.75)

        scaled_min = base_min * self.dialog_factor
        scaled_max = base_max * self.dialog_factor
        wait_seconds = random.uniform(scaled_min, scaled_max)
        wait_seconds = max(wait_seconds, 1.0)

        self.dialog_timer.start(int(wait_seconds * 1000))
        print(f"[INFO] Next dialog scheduled in ~{wait_seconds:.2f} seconds.")

    def show_dialog_random(self):
        if not self.rampage_mode:
            return

        self.dialog_text = random.choice(self.dialog_messages)
        self.dialog_visible = True
        self.update()
        self.hide_dialog_timer.start(self.original_hide_dialog_ms)

    def hide_dialog(self):
        self.dialog_visible = False
        self.update()
        # Only schedule next dialog if still in rampage
        if self.rampage_mode:
            self.schedule_next_dialog()

    ################################################################
    # SPRITE MOVEMENT
    ################################################################
    def update_sprite_position(self):
        """
        This is called ~60 times per second. We handle:
          - Rampage movement (chase cursor)
          - Rampage exit animation
          - Non-rampage runs
        """
        if self.rampage_exit_running:
            # Perform the exit animation
            elapsed_ms = self.rampage_exit_start_time.msecsTo(QtCore.QTime.currentTime())
            t = elapsed_ms / (self.rampage_exit_duration * 1000.0)

            if t >= 1.0:
                # Done with exit
                self.sprite_x = self.rampage_exit_end_pos.x()
                self.sprite_y = self.rampage_exit_end_pos.y()
                self.finalize_rampage_off()
            else:
                sx, sy = self.rampage_exit_start_pos.x(), self.rampage_exit_start_pos.y()
                ex, ey = self.rampage_exit_end_pos.x(), self.rampage_exit_end_pos.y()
                self.sprite_x = sx + (ex - sx) * t
                self.sprite_y = sy + (ey - sy) * t

            # even during exit animation, spawn paws if you like, or skip
            # we'll skip paw logic to keep it simple
            self.updateWindowMask()
            self.update()
            return

        if self.rampage_mode:
            # Original follow-cursor logic
            cursor_pos = QtGui.QCursor.pos()
            target_x = cursor_pos.x() - self.kiky_pixmap.width()
            target_y = cursor_pos.y() - self.kiky_pixmap.height() // 2

            dx = target_x - self.sprite_x
            dy = target_y - self.sprite_y
            self.vx += dx * self.accel
            self.vy += dy * self.accel

            self.vx *= self.friction
            self.vy *= self.friction

            self.sprite_x += self.vx - 1
            self.sprite_y += self.vy

            self.sprite_x += self.vx * self.parallax_factor
            self.sprite_y += self.vy * self.parallax_factor

            speed = math.hypot(self.vx, self.vy)
            dvx = self.vx - self.prev_vx
            dvy = self.vy - self.prev_vy
            dt = 0.016
            acceleration = math.hypot(dvx, dvy) / dt

            speed_threshold = 0.1
            accel_threshold = 0.5

            if speed > speed_threshold or acceleration > accel_threshold:
                current_paw_interval = max(
                    self.min_paw_interval,
                    self.base_paw_interval / (1.0 + self.spawn_rate_factor * speed)
                )
                now = QtCore.QTime.currentTime()
                if self.last_paw_time.msecsTo(now) >= current_paw_interval:
                    angle = math.degrees(math.atan2(self.vy, self.vx))
                    paw_x = self.sprite_x + (self.kiky_pixmap.width() // 2)
                    paw_y = self.sprite_y + (self.kiky_pixmap.height() // 2)

                    if self.paw_step_index % 2 == 1:
                        paw_y += 10

                    self.paw_traces.append({
                        'x': paw_x,
                        'y': paw_y,
                        'angle': angle,
                        'birth_time': now
                    })
                    self.last_paw_time = now
                    self.paw_step_index += 1

            self.prev_vx = self.vx
            self.prev_vy = self.vy

        else:
            # Non-rampage run
            if self.non_rampage_running:
                elapsed_ms = self.non_rampage_run_start_time.msecsTo(QtCore.QTime.currentTime())
                elapsed_s = elapsed_ms / 1000.0
                t = elapsed_s / self.non_rampage_duration

                if t >= 1.0:
                    t = 1.0
                    # Ensure final position is exactly the end
                    sx, sy = self.non_rampage_start.x(), self.non_rampage_start.y()
                    ex, ey = self.non_rampage_end.x(), self.non_rampage_end.y()
                    self.sprite_x = ex
                    self.sprite_y = ey
                    self.non_rampage_running = False

                    # Then place it off-screen
                    QtCore.QTimer.singleShot(500, self.move_sprite_offscreen)

                    # Allow picking a new run only after finishing the current run
                    self.non_rampage_can_trigger_run = True

                else:
                    sx, sy = self.non_rampage_start.x(), self.non_rampage_start.y()
                    ex, ey = self.non_rampage_end.x(), self.non_rampage_end.y()
                    self.sprite_x = sx + (ex - sx) * t
                    self.sprite_y = sy + (ey - sy) * t

                # --- Trailing paws in non-rampage ---
                dx = self.non_rampage_end.x() - self.non_rampage_start.x()
                dy = self.non_rampage_end.y() - self.non_rampage_start.y()
                speed = math.hypot(dx, dy) / self.non_rampage_duration  # approx speed
                if speed > 0.1:
                    now = QtCore.QTime.currentTime()
                    # interval logic
                    current_paw_interval = max(
                        self.min_paw_interval,
                        self.base_paw_interval / (1.0 + self.spawn_rate_factor * (speed / 50.0))
                    )
                    if self.last_paw_time.msecsTo(now) >= current_paw_interval:
                        angle = math.degrees(math.atan2(dy, dx))
                        paw_x = self.sprite_x + (self.kiky_pixmap.width() // 2)
                        paw_y = self.sprite_y + (self.kiky_pixmap.height() // 2)

                        if self.paw_step_index % 2 == 1:
                            paw_y += 10

                        self.paw_traces.append({
                            'x': paw_x,
                            'y': paw_y,
                            'angle': angle,
                            'birth_time': now
                        })
                        self.last_paw_time = now
                        self.paw_step_index += 1

                self.vx = 0
                self.vy = 0
                self.prev_vx = 0
                self.prev_vy = 0
            else:
                # Keep sprite off-screen
                self.sprite_x = -9999
                self.sprite_y = -9999

        self.updateWindowMask()
        self.update()

    def move_sprite_offscreen(self):
        """Helper to move sprite out of the screen after finishing run."""
        if not self.non_rampage_running:
            self.sprite_x = -9999
            self.sprite_y = -9999
            self.update()

    ################################################################
    # PICK OFFSCREEN POINT
    ################################################################
    def pick_offscreen_point(self):
        # Use the entire virtual desktop dimensions
        desktop = QtWidgets.QApplication.desktop()
        screen_rect = desktop.geometry()  # bounding rectangle over all monitors
        
        margin = 300 # How far offscreen you want to place the sprite
        side = random.choice(["left", "right", "top", "bottom"])

        if side == "left":
            x = screen_rect.left() - margin
            y = random.randint(screen_rect.top(), screen_rect.bottom())
        elif side == "right":
            x = screen_rect.right() + margin
            y = random.randint(screen_rect.top(), screen_rect.bottom())
        elif side == "top":
            x = random.randint(screen_rect.left(), screen_rect.right())
            y = screen_rect.top() - margin
        else:  # "bottom"
            x = random.randint(screen_rect.left(), screen_rect.right())
            y = screen_rect.bottom() + margin

        return QtCore.QPoint(x, y)

    ################################################################
    # NON-RAMPAGE RUN
    ################################################################
    def trigger_non_rampage_run(self):
        # Only trigger if not in rampage AND not exiting rampage
        if self.rampage_mode or self.rampage_exit_running or (not self.non_rampage_can_trigger_run):
            return

        # Start run across
        self.non_rampage_can_trigger_run = False  # block new triggers until done
        self.non_rampage_start = self.pick_offscreen_point()
        self.non_rampage_end = self.pick_offscreen_point()
        self.non_rampage_running = True
        self.non_rampage_run_start_time = QtCore.QTime.currentTime()

        self.sprite_x = self.non_rampage_start.x()
        self.sprite_y = self.non_rampage_start.y()
        print(f"[INFO] Non-rampage run from {self.non_rampage_start} to {self.non_rampage_end}")

    ################################################################
    # WINDOW MASK
    ################################################################
    def updateWindowMask(self):
        mask_region = QtGui.QRegion()

        # Sprite bounding rect
        if not self.kiky_pixmap.isNull():
            sprite_rect = QtCore.QRect(
                int(self.sprite_x),
                int(self.sprite_y),
                self.kiky_pixmap.width(),
                self.kiky_pixmap.height()
            )
            mask_region = mask_region.united(QtGui.QRegion(sprite_rect))

        # Paws
        for paw in self.paw_traces:
            paw_rect = QtCore.QRect(
                int(paw['x'] - self.paw_pixmap.width() // 2),
                int(paw['y'] - self.paw_pixmap.height() // 2),
                self.paw_pixmap.width(),
                self.paw_pixmap.height()
            )
            mask_region = mask_region.united(QtGui.QRegion(paw_rect))

        # Dialog bubble
        if self.dialog_visible and self.rampage_mode and not self.dialog_rect.isNull():
            mask_region = mask_region.united(QtGui.QRegion(self.dialog_rect))

        self.setMask(mask_region)

    ################################################################
    # TAKEOVER LOGIC (only in rampage)
    ################################################################
    def schedule_next_cursor_takeover(self):
        """Only schedule if in rampage mode."""
        if not self.rampage_mode:
            print("[INFO] Not in rampage mode => skipping cursor takeover scheduling.")
            self.random_start_timer.stop()
            return

        self.takeover_factor = max(self.min_factor, self.takeover_factor * 0.9)

        range_min = self.original_takeover_min * self.takeover_factor
        range_max = self.original_takeover_max * self.takeover_factor
        wait_seconds = random.uniform(range_min, range_max)
        wait_seconds = max(wait_seconds, 1.0)

        self.random_start_timer.start(int(wait_seconds * 1000))
        print(f"[INFO] Next takeover in ~{wait_seconds:.2f} seconds.")

    def start_cursor_takeover(self):
        """Only start if in rampage mode."""
        if not self.rampage_mode:
            print("[INFO] Not in rampage mode => ignoring start_cursor_takeover().")
            return

        if hasattr(self, "effect_active") and self.effect_active:
            return

        self.effect_active = True
        print("[INFO] Cursor takeover started.")

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BlankCursor)

        duration_min = self.original_effect_duration_min
        duration_max = self.original_effect_duration_max
        self.effect_duration = random.randint(duration_min, duration_max)
        self.effect_start_time = QtCore.QTime.currentTime()

        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        center = screen.center()
        QtGui.QCursor.setPos(center)
        print(f"[INFO] Cursor moved to screen center at ({center.x()}, {center.y()}).")

        # Block user mouse
        self.mouse_hook.start()

        self.cursor_move_start_time = None
        self.cursor_move_duration = 0
        self.from_pos = None
        self.to_pos = None
        self.cursor_move_timer.start(16)

    def stop_cursor_takeover(self):
        try:
            if not getattr(self, "effect_active", False):
                return

            self.effect_active = False
            print("[INFO] Cursor takeover ended.")

            QtWidgets.QApplication.restoreOverrideCursor()
            self.mouse_hook.stop()
            self.cursor_move_timer.stop()

            # Only schedule the next takeover if still in rampage
            if self.rampage_mode:
                self.schedule_next_cursor_takeover()

        except Exception as e:
            print(f"[ERROR] Exception in stop_cursor_takeover: {e}")
            self.mouse_hook.stop()
            QtWidgets.QApplication.restoreOverrideCursor()

    def pick_random_target(self):
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        corners = [
            screen.topLeft(),
            screen.topRight(),
            screen.bottomLeft(),
            screen.bottomRight()
        ]
        if random.random() < 0.5:
            return random.choice(corners)
        else:
            x = random.randint(screen.x(), screen.x() + screen.width())
            y = random.randint(screen.y(), screen.y() + screen.height())
            return QtCore.QPoint(x, y)

    def move_cursor_around(self):
        now = QtCore.QTime.currentTime()
        elapsed_ms_total = self.effect_start_time.msecsTo(now)
        if elapsed_ms_total >= self.effect_duration * 1000:
            self.stop_cursor_takeover()
            return

        if self.cursor_move_start_time is None:
            self.cursor_move_start_time = QtCore.QTime.currentTime()
            self.from_pos = QtGui.QCursor.pos()
            self.to_pos = self.pick_random_target()
            self.cursor_move_duration = random.uniform(0.5, 2.0)

            print(
                f"[INFO] Moving cursor from {self.from_pos} to {self.to_pos} "
                f"over {self.cursor_move_duration:.2f} sec."
            )

        elapsed_ms = self.cursor_move_start_time.msecsTo(now)
        t = elapsed_ms / (self.cursor_move_duration * 1000.0)

        if t >= 1.0:
            QtGui.QCursor.setPos(self.to_pos)
            print(f"[INFO] Cursor reached {self.to_pos}.")
            self.cursor_move_start_time = None
        else:
            sx, sy = self.from_pos.x(), self.from_pos.y()
            tx, ty = self.to_pos.x(), self.to_pos.y()
            new_x = sx + (tx - sx) * t
            new_y = sy + (ty - sy) * t
            QtGui.QCursor.setPos(int(new_x), int(new_y))

################################################################
# Main
################################################################

def main():
    app = QtWidgets.QApplication(sys.argv)
    desktop_sprite = DesktopSprite("kiky.png", "paw.png")
    desktop_sprite.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
