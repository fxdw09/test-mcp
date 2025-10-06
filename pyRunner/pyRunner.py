import sys
import os
import subprocess
import threading
import time
import locale
import codecs
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog, QSpinBox,
    QSystemTrayIcon, QMenu, QMessageBox, QListWidget, QGroupBox,
    QSplitter, QTabWidget, QCheckBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QAction, QFont

# 设置默认编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stderr, 'reconfigure') else None


class PythonRunnerThread(QThread):
    """Python脚本运行线程"""
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, float)  # 退出码和运行时间
    error_signal = pyqtSignal(str)

    def __init__(self, python_path, script_path, env_paths, timeout):
        super().__init__()
        self.python_path = python_path
        self.script_path = script_path
        self.env_paths = env_paths
        self.timeout = timeout
        self.process = None
        self.start_time = None
        self.should_stop = False

    def run(self):
        try:
            self.start_time = time.time()

            # 构建环境变量
            env = os.environ.copy()

            # 设置PYTHONIOENCODING环境变量为utf-8
            env['PYTHONIOENCODING'] = 'utf-8'

            if self.env_paths:
                current_path = env.get('PYTHONPATH', '')
                new_paths = ';'.join(self.env_paths)
                if current_path:
                    env['PYTHONPATH'] = f"{new_paths};{current_path}"
                else:
                    env['PYTHONPATH'] = new_paths

            # 启动进程，使用utf-8编码
            self.process = subprocess.Popen(
                [self.python_path, "-u", self.script_path],  # -u 参数强制Python使用无缓冲的标准流
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',  # 明确指定编码为utf-8
                errors='replace',  # 替换无法解码的字符
                env=env,
                bufsize=1,
                universal_newlines=True
            )

            # 读取输出
            while True:
                if self.should_stop:
                    self.process.terminate()
                    break

                output = self.process.stdout.readline()
                if output:
                    self.output_signal.emit(output.strip())
                elif self.process.poll() is not None:
                    break

                # 检查超时
                if self.timeout > 0 and time.time() - self.start_time > self.timeout:
                    self.process.terminate()
                    self.error_signal.emit(f"程序运行超时（{self.timeout}秒），已终止")
                    break

            # 获取剩余输出
            remaining_output, _ = self.process.communicate()
            if remaining_output:
                for line in remaining_output.split('\n'):
                    if line.strip():
                        self.output_signal.emit(line.strip())

            end_time = time.time()
            run_time = end_time - self.start_time
            exit_code = self.process.returncode

            self.finished_signal.emit(exit_code, run_time)

        except Exception as e:
            self.error_signal.emit(f"运行错误: {str(e)}")

    def stop(self):
        self.should_stop = True
        if self.process:
            self.process.terminate()


class PythonRunnerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.runner_thread = None
        self.init_ui()
        self.init_tray()

    def init_ui(self):
        self.setWindowTitle("Python脚本运行器")
        self.setGeometry(100, 100, 1000, 700)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局
        main_layout = QVBoxLayout(central_widget)

        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        # 上半部分：配置区域
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)

        # Python解释器选择
        interpreter_group = QGroupBox("Python解释器配置")
        interpreter_layout = QVBoxLayout(interpreter_group)

        interpreter_select_layout = QHBoxLayout()
        self.interpreter_path = QLineEdit()
        self.interpreter_path.setPlaceholderText("选择Python解释器路径")
        interpreter_select_btn = QPushButton("浏览")
        interpreter_select_btn.clicked.connect(self.select_interpreter)
        interpreter_select_layout.addWidget(QLabel("解释器路径:"))
        interpreter_select_layout.addWidget(self.interpreter_path)
        interpreter_select_layout.addWidget(interpreter_select_btn)
        interpreter_layout.addLayout(interpreter_select_layout)

        # 环境变量设置
        env_layout = QHBoxLayout()
        self.env_vars = QLineEdit()
        self.env_vars.setPlaceholderText("额外环境变量 (KEY=VALUE;KEY2=VALUE2)")
        env_layout.addWidget(QLabel("环境变量:"))
        env_layout.addWidget(self.env_vars)
        interpreter_layout.addLayout(env_layout)

        # 添加编码选择
        encoding_layout = QHBoxLayout()
        self.encoding_checkbox = QCheckBox("强制使用UTF-8编码")
        self.encoding_checkbox.setChecked(True)  # 默认选中
        encoding_layout.addWidget(self.encoding_checkbox)
        interpreter_layout.addLayout(encoding_layout)

        config_layout.addWidget(interpreter_group)

        # 脚本文件选择
        script_group = QGroupBox("脚本文件配置")
        script_layout = QVBoxLayout(script_group)

        script_select_layout = QHBoxLayout()
        self.script_path = QLineEdit()
        self.script_path.setPlaceholderText("选择要运行的Python脚本")
        script_select_btn = QPushButton("浏览")
        script_select_btn.clicked.connect(self.select_script)
        script_select_layout.addWidget(QLabel("脚本路径:"))
        script_select_layout.addWidget(self.script_path)
        script_select_layout.addWidget(script_select_btn)
        script_layout.addLayout(script_select_layout)

        config_layout.addWidget(script_group)

        # 依赖路径配置
        deps_group = QGroupBox("依赖路径配置")
        deps_layout = QVBoxLayout(deps_group)

        # 依赖路径列表
        deps_list_layout = QHBoxLayout()
        self.deps_list = QListWidget()
        self.deps_list.setMaximumHeight(100)

        deps_buttons_layout = QVBoxLayout()
        add_dep_btn = QPushButton("添加路径")
        add_dep_btn.clicked.connect(self.add_dependency_path)
        add_package_btn = QPushButton("添加包路径")
        add_package_btn.clicked.connect(self.add_package_path)
        remove_dep_btn = QPushButton("移除选中")
        remove_dep_btn.clicked.connect(self.remove_dependency)
        clear_deps_btn = QPushButton("清空")
        clear_deps_btn.clicked.connect(self.clear_dependencies)

        deps_buttons_layout.addWidget(add_dep_btn)
        deps_buttons_layout.addWidget(add_package_btn)
        deps_buttons_layout.addWidget(remove_dep_btn)
        deps_buttons_layout.addWidget(clear_deps_btn)
        deps_buttons_layout.addStretch()

        deps_list_layout.addWidget(self.deps_list)
        deps_list_layout.addLayout(deps_buttons_layout)
        deps_layout.addLayout(deps_list_layout)

        config_layout.addWidget(deps_group)

        # 运行控制
        control_group = QGroupBox("运行控制")
        control_layout = QHBoxLayout(control_group)

        control_layout.addWidget(QLabel("超时时间(秒):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 3600)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSpecialValueText("无限制")
        control_layout.addWidget(self.timeout_spin)

        control_layout.addStretch()

        self.run_btn = QPushButton("运行")
        self.run_btn.clicked.connect(self.run_script)
        self.run_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        control_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_script)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")
        control_layout.addWidget(self.stop_btn)

        config_layout.addWidget(control_group)

        splitter.addWidget(config_widget)

        # 下半部分：输出区域
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)

        output_layout.addWidget(QLabel("运行输出:"))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 9))
        output_layout.addWidget(self.output_text)

        # 状态信息
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.time_label = QLabel("运行时间: 0秒")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.time_label)
        output_layout.addLayout(status_layout)

        splitter.addWidget(output_widget)

        # 设置分割器比例
        splitter.setSizes([300, 400])

        # 清空输出按钮
        clear_btn = QPushButton("清空输出")
        clear_btn.clicked.connect(self.clear_output)
        main_layout.addWidget(clear_btn)

    def init_tray(self):
        """初始化系统托盘"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(self, "系统托盘", "系统不支持托盘功能")
            return

        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)

        # 创建托盘菜单
        tray_menu = QMenu()

        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)

        # 设置托盘图标（这里使用系统默认图标，实际使用时应该使用自定义图标）
        self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        self.tray_icon.show()

    def select_interpreter(self):
        """选择Python解释器"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Python解释器", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if file_path:
            self.interpreter_path.setText(file_path)

    def select_script(self):
        """选择Python脚本"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Python脚本", "", "Python文件 (*.py);;所有文件 (*)"
        )
        if file_path:
            self.script_path.setText(file_path)

    def add_dependency_path(self):
        """添加依赖路径"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择依赖路径")
        if dir_path:
            self.deps_list.addItem(f"路径: {dir_path}")

    def add_package_path(self):
        """添加包路径"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择包路径")
        if dir_path:
            self.deps_list.addItem(f"包: {dir_path}")

    def remove_dependency(self):
        """移除选中的依赖"""
        current_row = self.deps_list.currentRow()
        if current_row >= 0:
            self.deps_list.takeItem(current_row)

    def clear_dependencies(self):
        """清空依赖列表"""
        self.deps_list.clear()

    def get_dependency_paths(self):
        """获取所有依赖路径"""
        paths = []
        for i in range(self.deps_list.count()):
            item_text = self.deps_list.item(i).text()
            if item_text.startswith("路径: "):
                paths.append(item_text[4:])
            elif item_text.startswith("包: "):
                paths.append(item_text[3:])
        return paths

    def run_script(self):
        """运行脚本"""
        if not self.interpreter_path.text():
            QMessageBox.warning(self, "警告", "请选择Python解释器")
            return

        if not self.script_path.text():
            QMessageBox.warning(self, "警告", "请选择要运行的脚本")
            return

        if not os.path.exists(self.interpreter_path.text()):
            QMessageBox.warning(self, "警告", "Python解释器路径不存在")
            return

        if not os.path.exists(self.script_path.text()):
            QMessageBox.warning(self, "警告", "脚本文件不存在")
            return

        # 清空输出
        self.output_text.clear()

        # 获取配置
        python_path = self.interpreter_path.text()
        script_path = self.script_path.text()
        env_paths = self.get_dependency_paths()
        timeout = self.timeout_spin.value()

        # 添加自定义环境变量
        custom_env = {}
        if self.env_vars.text().strip():
            try:
                for env_pair in self.env_vars.text().split(';'):
                    if '=' in env_pair:
                        key, value = env_pair.split('=', 1)
                        custom_env[key.strip()] = value.strip()
            except Exception as e:
                QMessageBox.warning(self, "警告", f"环境变量格式错误: {str(e)}")
                return

        # 如果选中了强制UTF-8编码，添加相应的环境变量
        if self.encoding_checkbox.isChecked():
            custom_env['PYTHONIOENCODING'] = 'utf-8'
            # 添加一个特殊的环境变量，告诉脚本使用UTF-8编码
            custom_env['PYTHONLEGACYWINDOWSFSENCODING'] = '0'
            custom_env['PYTHONLEGACYWINDOWSSTDIO'] = '0'

        # 创建并启动运行线程
        self.runner_thread = PythonRunnerThread(python_path, script_path, env_paths, timeout)
        self.runner_thread.output_signal.connect(self.append_output)
        self.runner_thread.finished_signal.connect(self.on_script_finished)
        self.runner_thread.error_signal.connect(self.append_error)

        # 添加自定义环境变量
        for key, value in custom_env.items():
            os.environ[key] = value

        self.runner_thread.start()

        # 更新UI状态
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("运行中...")

        # 启动计时器
        self.start_time = time.time()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 每秒更新一次

    def stop_script(self):
        """停止脚本"""
        if self.runner_thread:
            self.runner_thread.stop()
            self.runner_thread.wait()

        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")

        if hasattr(self, 'timer'):
            self.timer.stop()

    def append_output(self, text):
        """添加输出文本"""
        self.output_text.append(text)
        # 自动滚动到底部
        cursor = self.output_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.output_text.setTextCursor(cursor)

    def append_error(self, text):
        """添加错误文本"""
        self.output_text.append(f"<span style='color: red;'>{text}</span>")

    def on_script_finished(self, exit_code, run_time):
        """脚本运行完成"""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if hasattr(self, 'timer'):
            self.timer.stop()

        status_text = f"完成 (退出码: {exit_code}, 运行时间: {run_time:.2f}秒)"
        self.status_label.setText(status_text)
        self.time_label.setText(f"运行时间: {run_time:.2f}秒")

        self.append_output(f"\n=== 脚本执行完成 ===")
        self.append_output(f"退出码: {exit_code}")
        self.append_output(f"运行时间: {run_time:.2f}秒")

    def update_time(self):
        """更新运行时间显示"""
        if hasattr(self, 'start_time'):
            elapsed = time.time() - self.start_time
            self.time_label.setText(f"运行时间: {elapsed:.1f}秒")

    def clear_output(self):
        """清空输出"""
        self.output_text.clear()

    def closeEvent(self, event):
        """关闭事件处理"""
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    def tray_icon_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def show_window(self):
        """显示主窗口"""
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_application(self):
        """退出应用程序"""
        if self.runner_thread and self.runner_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认退出", "脚本正在运行，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.runner_thread.stop()
                self.runner_thread.wait()
            else:
                return

        QApplication.quit()


def main():
    # 设置默认编码为UTF-8
    if sys.platform.startswith('win'):
        # 在Windows上设置控制台编码为UTF-8
        os.system('chcp 65001 > nul')

    app = QApplication(sys.argv)

    # 设置应用程序不在任务栏显示时退出
    app.setQuitOnLastWindowClosed(False)

    window = PythonRunnerGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()