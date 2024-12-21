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


# MouseHook class to encapsulate hooking/unhooking
class MouseHook:
    def __init__(self):
        self.hHook = None
        self._callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
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
                # Pass other events if desired (click, scroll) or block them similarly
            return user32.CallNextHookEx(self.hHook, nCode, wParam, lParam)

        # Store the callback so it isn't garbage-collected
        self._hook_callback = self._callback_type(low_level_mouse_proc)

        # Set the hook
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
# Main DesktopSprite application
################################################################

class DesktopSprite(QtWidgets.QWidget):
    def __init__(self, sprite_path, paw_path):
        super().__init__()

        # Window setup
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Main sprite
        self.sprite = QtGui.QPixmap(sprite_path)
        self.resize(self.sprite.size())

        # Paw trace sprite
        self.paw_pixmap = QtGui.QPixmap(paw_path)
        self.paw_traces = []

        # Current position and velocity
        self.current_x = 0
        self.current_y = 0
        self.velocity_x = 0
        self.velocity_y = 0

        # Movement parameters
        self.accel = 0.03
        self.friction = 0.75
        self.parallax_factor = 0.15

        # Paw fading time (milliseconds)
        self.fade_time = 2000

        # Update timer (roughly 60 FPS)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_sprite_position)
        self.timer.start(16)

        # Flags and timers for random takeover
        self.effect_active = False
        self.random_start_timer = QtCore.QTimer()
        self.random_start_timer.setSingleShot(True)
        self.random_start_timer.timeout.connect(self.start_cursor_takeover)

        # Timer that runs while the cursor is being “taken over”
        self.cursor_move_timer = QtCore.QTimer()
        self.cursor_move_timer.timeout.connect(self.move_cursor_around)

        # For parametric movement (aggressive random)
        self.cursor_move_start_time = None
        self.cursor_move_duration = 0
        self.from_pos = None
        self.to_pos = None

        # Our low-level mouse hook manager
        self.mouse_hook = MouseHook()

        # Initialize the random schedule
        self.schedule_next_cursor_takeover()

    # ----------------------------------------------------------------------
    # Random scheduling
    # ----------------------------------------------------------------------
    def schedule_next_cursor_takeover(self):
        """
        Wait a random time between 30 and 180 seconds before starting
        the effect again.
        """
        wait_seconds = random.randint(30, 180)
        self.random_start_timer.start(wait_seconds * 1000)
        print(f"[INFO] Next takeover in {wait_seconds} seconds.")

    def start_cursor_takeover(self):
        """
        Hides the cursor, blocks user mouse input (via low-level hook),
        and starts aggressively moving it for a random time (10–15 seconds).
        Also, moves the cursor into the middle of the image right away.
        """
        if self.effect_active:
            return

        self.effect_active = True
        print("[INFO] Cursor takeover started.")

        # Hide the system-wide cursor
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BlankCursor)

        # Decide how long the effect will last (10–15 seconds)
        self.effect_duration = random.randint(10, 15)
        self.effect_start_time = QtCore.QTime.currentTime()

        # Center the sprite window on the screen
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

        # Move the cursor to the center of the sprite window
        sprite_center_x = self.x() + self.width() // 2
        sprite_center_y = self.y() + self.height() // 2
        QtGui.QCursor.setPos(sprite_center_x, sprite_center_y)
        print(f"[INFO] Cursor moved to sprite center at ({sprite_center_x}, {sprite_center_y}).")

        # LOW-LEVEL HOOK to block the user's actual mouse movements
        self.mouse_hook.start()

        # Reset param-based movement state
        self.cursor_move_start_time = None
        self.cursor_move_duration = 0
        self.from_pos = None
        self.to_pos = None

        # Start moving the cursor ~60 FPS
        self.cursor_move_timer.start(16)

    def stop_cursor_takeover(self):
        """
        Ends the cursor takeover, restores normal cursor, unhooks mouse,
        and schedules the next random takeover.
        """
        try:
            if not self.effect_active:
                return

            self.effect_active = False
            print("[INFO] Cursor takeover ended.")

            # Restore normal cursor
            QtWidgets.QApplication.restoreOverrideCursor()

            # Stop blocking user mouse input
            self.mouse_hook.stop()

            # Stop moving the cursor
            self.cursor_move_timer.stop()

            # Schedule the next takeover
            self.schedule_next_cursor_takeover()
        except Exception as e:
            print(f"[ERROR] Exception in stop_cursor_takeover: {e}")
            self.mouse_hook.stop()
            QtWidgets.QApplication.restoreOverrideCursor()

    # ----------------------------------------------------------------------
    # Aggressive random movement
    # ----------------------------------------------------------------------
    def pick_random_target(self):
        """
        Return a (QPoint) random target on the screen:
          - Possibly corners, or random anywhere in the screen
        """
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()

        corners = [
            screen.topLeft(),
            screen.topRight(),
            screen.bottomLeft(),
            screen.bottomRight()
        ]

        # 50% chance we pick a corner, 50% we pick a random point
        if random.random() < 0.5:
            return random.choice(corners)
        else:
            x = random.randint(screen.x(), screen.x() + screen.width())
            y = random.randint(screen.y(), screen.y() + screen.height())
            return QtCore.QPoint(x, y)

    def move_cursor_around(self):
        """
        Aggressively moves the (invisible) cursor toward random targets.
        When we reach a target or time is up, pick a new target.
        """
        # Check if we've exceeded our effect duration
        now = QtCore.QTime.currentTime()
        elapsed_ms_total = self.effect_start_time.msecsTo(now)
        if elapsed_ms_total >= self.effect_duration * 1000:
            self.stop_cursor_takeover()
            return

        # If we don't have an active interpolation, pick a new random target
        if self.cursor_move_start_time is None:
            self.cursor_move_start_time = QtCore.QTime.currentTime()
            self.from_pos = QtGui.QCursor.pos()
            self.to_pos = self.pick_random_target()

            # Random duration to move from 'from_pos' to 'to_pos' (0.5s to 2s)
            self.cursor_move_duration = random.uniform(0.5, 2.0)
            print(
                f"[INFO] Moving cursor from {self.from_pos} to {self.to_pos} over {self.cursor_move_duration:.2f} seconds.")

        # Interpolate from from_pos to to_pos
        elapsed_ms = self.cursor_move_start_time.msecsTo(now)
        t = elapsed_ms / (self.cursor_move_duration * 1000.0)

        if t >= 1.0:
            # We’ve reached the target (or time is up for this leg)
            QtGui.QCursor.setPos(self.to_pos)
            print(f"[INFO] Cursor reached target at {self.to_pos}.")
            # Force picking a new target next update
            self.cursor_move_start_time = None
        else:
            # Linear interpolation
            sx, sy = self.from_pos.x(), self.from_pos.y()
            tx, ty = self.to_pos.x(), self.to_pos.y()

            new_x = sx + (tx - sx) * t
            new_y = sy + (ty - sy) * t

            QtGui.QCursor.setPos(int(new_x), int(new_y))
            # print(f"[DEBUG] Cursor moving to ({int(new_x)}, {int(new_y)})")

    # ----------------------------------------------------------------------
    # Normal sprite drawing / movement (with parallax)
    # ----------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        now = QtCore.QTime.currentTime()
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

        # Finally, draw the main sprite on top
        painter.drawPixmap(0, 0, self.sprite)

    def update_sprite_position(self):
        """
        Always do normal chase + parallax logic.
        """
        cursor_pos = QtGui.QCursor.pos()

        # We want the sprite to be on the left of the cursor
        target_x = cursor_pos.x() - self.width()
        target_y = cursor_pos.y() - self.height() // 2

        # Calculate the difference from the sprite's current position to the target
        dx = target_x - self.current_x
        dy = target_y - self.current_y

        # Accelerate the sprite towards the target
        self.velocity_x += dx * self.accel
        self.velocity_y += dy * self.accel

        # Apply friction
        self.velocity_x *= self.friction
        self.velocity_y *= self.friction

        # Update current position
        self.current_x += self.velocity_x - 1
        self.current_y += self.velocity_y

        # Parallax offset
        parallax_x = self.velocity_x * self.parallax_factor
        parallax_y = self.velocity_y * self.parallax_factor

        final_x = self.current_x + parallax_x
        final_y = self.current_y + parallax_y

        # Move sprite
        self.move(int(final_x), int(final_y))

        # Create a new paw trace each update
        speed = math.hypot(self.velocity_x, self.velocity_y)
        if speed > 0.01:
            angle = math.degrees(math.atan2(self.velocity_y, self.velocity_x))
        else:
            angle = 0

        self.paw_traces.append({
            'x': final_x + self.width() // 2,
            'y': final_y + self.height() // 2,
            'angle': angle,
            'birth_time': QtCore.QTime.currentTime()
        })

        self.update()


def main():
    app = QtWidgets.QApplication(sys.argv)
    desktop_sprite = DesktopSprite("image.png", "paws.png")
    desktop_sprite.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
