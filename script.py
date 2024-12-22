import sys
import math
import random
import ctypes
from ctypes import wintypes
from PyQt5 import QtCore, QtGui, QtWidgets

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
                # Pass other events if desired (click, scroll) or block similarly
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

        # ------------------------------------
        # Load bubble sprite for the dialogue
        # ------------------------------------
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

        # Timers
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_sprite_position)
        self.timer.start(16)

        self.effect_active = False
        self.random_start_timer = QtCore.QTimer()
        self.random_start_timer.setSingleShot(True)
        self.random_start_timer.timeout.connect(self.start_cursor_takeover)

        self.cursor_move_timer = QtCore.QTimer()
        self.cursor_move_timer.timeout.connect(self.move_cursor_around)
        self.cursor_move_start_time = None
        self.cursor_move_duration = 0
        self.from_pos = None
        self.to_pos = None

        # Mouse hook manager
        self.mouse_hook = MouseHook()

        # Schedule the first random takeover
        self.schedule_next_cursor_takeover()

        # Track previous velocity
        self.prev_vx = 0
        self.prev_vy = 0

        # ------------------------------------------------------------------
        #  DIALOG / "SPEECH BUBBLE" LOGIC
        # ------------------------------------------------------------------
        self.dialog_messages = [
            "Hope Santa will finally seat on a diet",
            "If two vegans are having a fight is it still considered a beef?",
            "Hungry? Eat the government!",
            "Do not have money? Have you ever tried tax evasion?",
            "I think that Каnуе West is super overrated",
        ]

        self.dialog_visible = False
        self.dialog_text = ""
        self.dialog_timer = QtCore.QTimer()
        self.dialog_timer.setSingleShot(True)
        self.dialog_timer.timeout.connect(self.show_dialog_random)

        # Start first random dialog schedule
        self.schedule_next_dialog()

        self.hide_dialog_timer = QtCore.QTimer()
        self.hide_dialog_timer.setSingleShot(True)
        self.hide_dialog_timer.timeout.connect(self.hide_dialog)

        # We'll store the bubble geometry here so we can add it to the mask.
        self.dialog_rect = QtCore.QRect()

        # Shape the window to the combined region of sprite + paw traces + bubble
        self.updateWindowMask()

    ################################################################
    # Paint Event (draw paws first, then sprite, then bubble + text)
    ################################################################
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        now = QtCore.QTime.currentTime()

        # 1) Draw paw traces behind the sprite
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

        # 2) Draw the main sprite
        painter.save()
        painter.drawPixmap(int(self.sprite_x),
                        int(self.sprite_y),
                        self.sprite)
        painter.restore()

        # 3) Draw the bubble + text if visible
        if self.dialog_visible and not self.sprite.isNull():
            font = QtGui.QFont()
            font.setPointSize(12)  # Set font size for bubble text
            painter.setFont(font)
            metrics = QtGui.QFontMetrics(font)

            # Calculate bounding box for text
            text_margin = 20  # Space around the text
            max_width = 350  # Maximum width for word wrapping
            text_bounding_rect = metrics.boundingRect(0, 0, max_width, 0,
                                                    QtCore.Qt.TextWordWrap, self.dialog_text)

            # Calculate required bubble dimensions with extra height for tail
            bubble_width = text_bounding_rect.width() + 2 * text_margin
            bubble_height = text_bounding_rect.height() + 2 * text_margin

            # Add extra height for the tail
            tail_margin = max(20, int(0.5 * bubble_height))  # Adjust tail size proportionally
            bubble_height += tail_margin

            # Resize the bubble sprite to fit the text dimensions with tail
            if not self.bubble_pixmap.isNull():
                self.bubble_pixmap = self.bubble_pixmap.scaled(
                    bubble_width, bubble_height,
                    QtCore.Qt.KeepAspectRatioByExpanding,
                    QtCore.Qt.SmoothTransformation
                )

            # Position the bubble to the left of the sprite
            bubble_x = int(self.sprite_x) - bubble_width - 30
            bubble_y = int(self.sprite_y)

            # Ensure the bubble stays within screen bounds
            screen_geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
            if bubble_x < 0:
                bubble_x = 0
            if bubble_y + bubble_height > screen_geo.height():
                bubble_y = screen_geo.height() - bubble_height

            # Update dialog rect for the mask
            self.dialog_rect = QtCore.QRect(bubble_x, bubble_y, bubble_width, bubble_height)

            # Draw the bubble sprite
            painter.save()
            painter.drawPixmap(bubble_x, bubble_y, self.bubble_pixmap)
            painter.restore()

            # Draw the text inside the bubble
            text_rect = QtCore.QRect(
                bubble_x + text_margin,
                bubble_y + text_margin,
                text_bounding_rect.width(),
                text_bounding_rect.height()
            )
            painter.save()
            painter.setPen(QtCore.Qt.black)
            painter.drawText(text_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop | QtCore.Qt.TextWordWrap, self.dialog_text)
            painter.restore()
        else:
            # No dialog => clear the stored rect
            self.dialog_rect = QtCore.QRect()

    ################################################################
    # Dialog logic
    ################################################################
    def schedule_next_dialog(self):
        """Schedule the next random appearance of the dialog in [5..7] seconds."""
        wait_seconds = random.randint(5, 7)
        self.dialog_timer.start(wait_seconds * 1000)
        print(f"[INFO] Next dialog scheduled in {wait_seconds} seconds.")

    def show_dialog_random(self):
        """Show a random dialog message."""
        self.dialog_text = random.choice(self.dialog_messages)
        self.dialog_visible = True
        self.update()  # Force paint => the rect is updated in paintEvent

        # Hide the dialog after 5 seconds
        self.hide_dialog_timer.start(5000)

    def hide_dialog(self):
        """Hide the dialog, then schedule another random appearance."""
        self.dialog_visible = False
        self.update()
        self.schedule_next_dialog()

    ################################################################
    # Normal sprite following logic
    ################################################################
    def update_sprite_position(self):
        cursor_pos = QtGui.QCursor.pos()

        # Aim left of the cursor
        target_x = cursor_pos.x() - self.sprite.width()
        target_y = cursor_pos.y() - self.sprite.height() // 2

        dx = target_x - self.sprite_x
        dy = target_y - self.sprite_y
        self.vx += dx * self.accel
        self.vy += dy * self.accel

        # Apply friction
        self.vx *= self.friction
        self.vy *= self.friction

        # Update position
        self.sprite_x += self.vx - 1
        self.sprite_y += self.vy

        # Optional parallax
        self.sprite_x += self.vx * self.parallax_factor
        self.sprite_y += self.vy * self.parallax_factor

        # Calculate speed & acceleration
        speed = math.hypot(self.vx, self.vy)
        dvx = self.vx - self.prev_vx
        dvy = self.vy - self.prev_vy
        dt = 0.016
        acceleration = math.hypot(dvx, dvy) / dt

        # Thresholds for spawning paws
        speed_threshold = 0.1
        accel_threshold = 0.5

        # Spawn paws if velocity OR acceleration is above threshold
        if speed > speed_threshold or acceleration > accel_threshold:
            current_paw_interval = max(
                self.min_paw_interval,
                self.base_paw_interval / (1.0 + self.spawn_rate_factor * speed)
            )
            now = QtCore.QTime.currentTime()
            if self.last_paw_time.msecsTo(now) >= current_paw_interval:
                angle = math.degrees(math.atan2(self.vy, self.vx))

                # Center horizontally at bottom of sprite
                paw_x = self.sprite_x + (self.sprite.width() // 2)
                paw_y = self.sprite_y + (self.sprite.height() // 2)

                # Slight offset every other paw
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

        # Save previous velocity
        self.prev_vx = self.vx
        self.prev_vy = self.vy

        self.updateWindowMask()
        self.update()

    def updateWindowMask(self):
        """Ensure the window mask includes sprite, paws, AND bubble."""
        mask_region = QtGui.QRegion()

        # Sprite bounding rect
        if not self.sprite.isNull():
            sprite_rect = QtCore.QRect(int(self.sprite_x),
                                       int(self.sprite_y),
                                       self.sprite.width(),
                                       self.sprite.height())
            mask_region = mask_region.united(QtGui.QRegion(sprite_rect))

        # Paw bounding rects
        for paw in self.paw_traces:
            paw_rect = QtCore.QRect(
                int(paw['x'] - self.paw_pixmap.width() // 2),
                int(paw['y'] - self.paw_pixmap.height() // 2),
                self.paw_pixmap.width(),
                self.paw_pixmap.height()
            )
            mask_region = mask_region.united(QtGui.QRegion(paw_rect))

        # Bubble bounding rect
        if self.dialog_visible and not self.dialog_rect.isNull():
            mask_region = mask_region.united(QtGui.QRegion(self.dialog_rect))

        self.setMask(mask_region)

    ################################################################
    # Random scheduling + takeover logic
    ################################################################
    def schedule_next_cursor_takeover(self):
        wait_seconds = random.randint(30, 180)
        self.random_start_timer.start(wait_seconds * 1000)
        print(f"[INFO] Next takeover in {wait_seconds} seconds.")

    def start_cursor_takeover(self):
        if self.effect_active:
            return

        self.effect_active = True
        print("[INFO] Cursor takeover started.")

        # Hide the system-wide cursor
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BlankCursor)

        # Duration
        self.effect_duration = random.randint(10, 15)
        self.effect_start_time = QtCore.QTime.currentTime()

        # Move cursor to center
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        center = screen.center()
        QtGui.QCursor.setPos(center)
        print(f"[INFO] Cursor moved to screen center at ({center.x()}, {center.y()}).")

        # Block user mouse input
        self.mouse_hook.start()

        # Reset
        self.cursor_move_start_time = None
        self.cursor_move_duration = 0
        self.from_pos = None
        self.to_pos = None

        # Start the takeover movement
        self.cursor_move_timer.start(16)

    def stop_cursor_takeover(self):
        try:
            if not self.effect_active:
                return

            self.effect_active = False
            print("[INFO] Cursor takeover ended.")

            # Restore cursor
            QtWidgets.QApplication.restoreOverrideCursor()

            # Unblock user mouse
            self.mouse_hook.stop()

            # Stop movement
            self.cursor_move_timer.stop()

            # Schedule next
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
            # Reached target
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
    desktop_sprite = DesktopSprite("image.png", "paw.png")
    desktop_sprite.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
