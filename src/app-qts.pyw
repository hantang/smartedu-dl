"""
图形界面版本（PySide6实现）：智慧教育平台资源下载工具
"""

import argparse
import logging
import time
from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui

from tools.downloader import download_files_tk, fetch_all_data
from tools.parser import extract_resource_url, parse_urls
from tools.parser2 import fetch_metadata, gen_url_from_tags, query_metadata
from tools.utils import base64_to_image
from tools.theme import set_theme, set_dpi_scale
from tools.parser import RESOURCE_DICT
from tools.logo import DESCRIBES, LOGO_TEXT
from tools.icons import ICON_LARGE, ICON_SMALL


RESOURCE_FORMATS = ["pdf", "mp3", "ogg", "jpg", "m3u8", "superboard"]
RESOURCE_NAMES = ["文档", "音频", "音频", "图片", "视频", "白板"]


def display_results(results: list, elapsed_time: float):
    """展示下载结果统计"""
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count

    messages = [
        ["总计文件", str(len(results))],
        ["成功下载", f"{success_count}"],
        ["下载失败", f"{failed_count}"],
        ["总用时", f"{elapsed_time:.1f}秒"],
    ]
    return "\n".join([": ".join(v) for v in messages])


def update_labels_wraplength(event, labels, scale=1.0, delta=20, frame=None):
    # 更新标签的wraplength
    if not labels:
        return
    if frame:
        width = frame.width()
    elif event:
        width = event.width()
    else:
        width = labels[0].parent().width()
    wraplength = int(width - delta * scale)

    for label in labels:
        label.setWordWrap(True)
        label.setFixedWidth(wraplength)


class BookSelectorFrame(QtWidgets.QFrame):
    """自定义选择框架"""

    def __init__(self, parent, fonts, font_size, scale=1.0, os_name=None):
        super().__init__(parent)

        self.fonts = fonts
        self.font_size = font_size
        self.scale = scale
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)
        self.checkbox_height = int(100 * scale)

        # 初始化属性
        self.hier_dict = None
        self.tag_dict = None
        self.id_dict = None
        self.frame_names = ["选择课本", "选择教材"]
        self.level_hiers = []
        self.level_options = []  # 下拉框数据，[id, name]

        self.selected_items = set()  # 多选框选中的条目
        self.checkbox_list = []  # 多选框
        self.combobox_list = []  # 下拉框

        # 创建左右两个部分
        self.books_frame = QtWidgets.QGroupBox(self.frame_names[0])
        self.hierarchy_frame = QtWidgets.QGroupBox(self.frame_names[1])

        self.setup_books_frame()
        self.setup_hierarchy_frame()

    def setup_books_frame(self):
        """设置课本部分"""
        # 上半部分：多选框的frame（滚动条）
        checkbox_frame = QtWidgets.QFrame(self.books_frame)
        checkbox_layout = QtWidgets.QVBoxLayout(checkbox_frame)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)

        # 创建ScrollArea
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scrollable_frame = QtWidgets.QWidget()
        self.scroll_area.setWidget(self.scrollable_frame)

        checkbox_layout.addWidget(self.scroll_area)
        self.books_frame.setLayout(checkbox_layout)

        # 设置最大高度
        checkbox_frame.setFixedHeight(self.checkbox_height)  # 设置最大高度
        checkbox_frame.setLayout(checkbox_layout)
        checkbox_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # 下半部分：全选和取消全选按钮
        btn_frame = QtWidgets.QFrame(self.books_frame)
        btn_frame_layout = QtWidgets.QHBoxLayout(btn_frame)
        self.select_all_btn = QtWidgets.QPushButton("全选")
        self.deselect_all_btn = QtWidgets.QPushButton("取消全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        btn_frame_layout.addWidget(self.select_all_btn)
        btn_frame_layout.addWidget(self.deselect_all_btn)
        self.select_all_btn.setEnabled(False)
        self.deselect_all_btn.setEnabled(False)

        checkbox_layout.addWidget(btn_frame)

    def setup_hierarchy_frame(self):
        """设置教材层级部分"""
        # 上半部分：下拉框的frame
        self.combo_frame = QtWidgets.QFrame(self.hierarchy_frame)
        self.combo_layout = QtWidgets.QVBoxLayout(self.combo_frame)

        # 下半部分：查询按钮
        query_btn_frame = QtWidgets.QFrame(self.hierarchy_frame)
        query_btn_layout = QtWidgets.QHBoxLayout(query_btn_frame)

        self.query_btn = QtWidgets.QPushButton("查询")
        self.query_btn.clicked.connect(self.query_data)
        query_btn_layout.addWidget(self.query_btn)

        self.combo_frame.setLayout(self.combo_layout)
        self.hierarchy_frame.setLayout(query_btn_layout)

    def query_data(self):
        """查询数据并更新下拉框"""
        # 获取第一级数据
        if self.hier_dict is None:
            self.hierarchy_frame.setTitle("联网查询教材数据中……")
            self.hier_dict, self.tag_dict, self.id_dict = fetch_metadata(None)

        if self.hier_dict:
            logging.debug(f"hier_dict = {len(self.hier_dict)}")
            self.hierarchy_frame.setTitle("查询完成")
            self.hierarchy_frame.setTitle(self.frame_names[1])
            self.update_frame(0)
        else:
            self.update_frame(-1, -1)
            QtWidgets.QMessageBox.critical(self, "错误", "获取数据失败，请稍后再试")

    def update_frame(self, index):
        """更新层级和课本"""
        self._destroy_combobox(index)
        self.update_checkbox(None)
        self.level_options = []
        self.level_hiers = []
        if index < 0:
            return

        self.level_hiers = [self.hier_dict]
        self.level_options = [()]
        selected_key = self.hier_dict["next"][0]
        _, name, options = self._query(selected_key)

        # 创建第一个下拉框
        self.create_combobox(0, name, options)

    def create_combobox(self, index, name, options):
        self._destroy_combobox(index + 1)
        self.update_checkbox(None)

        frame = QtWidgets.QFrame(self.combo_frame)
        frame_layout = QtWidgets.QVBoxLayout(frame)
        frame.setLayout(frame_layout)

        level_count = len(self.level_options) - 1
        label = QtWidgets.QLabel(f"{level_count}. 【{name}】")
        frame_layout.addWidget(label)

        option_names = [op[1] for op in options]
        cb = QtWidgets.QComboBox()
        cb.addItems(option_names)
        cb.currentIndexChanged.connect(lambda: self.on_combobox_select(index, cb.currentText()))
        frame_layout.addWidget(cb)

        self.combobox_list.append([label, cb, frame])

        if len(option_names) == 0:
            self.hierarchy_frame.setTitle(f"{self.frame_names[1]}: {name} 数据为空")
        else:
            self.hierarchy_frame.setTitle(self.frame_names[1])

    def on_combobox_select(self, index: int, value: str):
        """处理选事件"""
        logging.debug(f"on_combobox_select index={index}, value={value}")
        self._destroy_combobox(index + 1)
        self.update_checkbox(None)

        # 查找选中项对应的key
        selected_key = None
        current_options = self.level_options[-1]
        for key, name in current_options:
            if name == value:
                selected_key = key
                break
        logging.debug(f"selected_key = {selected_key}, current_options = {current_options}")

        if selected_key:
            level, name, options = self._query(selected_key)
            # 创建多选框或者，下一级下拉框
            if level == -1:
                self.update_checkbox(options)
            else:
                self.create_combobox(index + 1, name, options)

    def _query(self, key):
        # 查询下一个下拉框数据
        current_hier_dict = self.level_hiers[-1]
        level, name, options = query_metadata(key, current_hier_dict, self.tag_dict, self.id_dict)
        self.level_hiers.append(current_hier_dict[key])
        self.level_options.append(options)

        return level, name, options

    def _destroy_combobox(self, index):
        index2 = max(index, 0)
        # 清除现有的下拉框和多选框
        for widgets in self.combobox_list[index2:]:
            for w in widgets:
                w.deleteLater()
        self.combobox_list = self.combobox_list[:index2]

        self.level_hiers = self.level_hiers[: index2 + 1]
        self.level_options = self.level_options[: index2 + 1]

    def update_checkbox(self, options):
        for widget in self.scrollable_frame.children():
            widget.deleteLater()

        self.checkbox_list = []
        self.selected_items = set()
        logging.debug(f"=>>> options = {options}")
        if not options:
            self.select_all_btn.setEnabled(False)
            self.deselect_all_btn.setEnabled(False)
            self.books_frame.setTitle(self.frame_names[0])
            if options is not None and len(options) == 0:
                self.books_frame.setTitle(f"{self.frame_names[0]}: 数据为空")
            return

        width = len(str(len(options)))
        for i, (book_id, book_name) in enumerate(options):
            var = QtCore.pyqtSignal()
            var.set(False)
            frame = QtWidgets.QFrame(self.scrollable_frame)
            frame_layout = QtWidgets.QHBoxLayout(frame)
            frame.setLayout(frame_layout)
            cb = QtWidgets.QCheckBox(f"{i + 1:0{width}d}. {book_name}")
            cb.stateChanged.connect(lambda state, id=book_id: self.toggle_checkbox_selection(id, state))
            frame_layout.addWidget(cb)
            self.checkbox_list.append((var, cb))

        if options:
            self.select_all_btn.setEnabled(True)
            self.deselect_all_btn.setEnabled(True)
            self.books_frame.setTitle(f"{self.frame_names[0]}: 共 {len(options)} 项资源")

    def toggle_checkbox_selection(self, book_id: str, state):
        """切换选择状态"""
        if state == QtCore.Qt.Checked:
            self.selected_items.add(book_id)
        else:
            self.selected_items.remove(book_id)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.setTitle(f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def select_all(self):
        """全选"""
        self.selected_items = set([op[0] for op in self.level_options[-1]])
        for var in self.checkbox_list:
            var[0].set(True)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.setTitle(f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def deselect_all(self):
        """取消全选"""
        self.selected_items = set()
        for var in self.checkbox_list:
            var[0].set(False)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.setTitle(f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def get_selected_urls(self) -> list[str]:
        """获取选中的URL列表"""
        return gen_url_from_tags(list(self.selected_items))


class InputURLAreaFrame(QtWidgets.QFrame):
    """手动输入面板"""

    def __init__(self, parent, fonts, font_size, scale=1.0, os_name=None):
        super().__init__(parent)
        self.fonts = fonts
        self.font_size = font_size
        self.scale = scale
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)

        self.setup_ui()

    def setup_ui(self):
        """初始化UI"""

        # 创建输入区域
        input_frame = QtWidgets.QGroupBox("输入URL（每行一个）")
        input_layout = QtWidgets.QVBoxLayout(input_frame)

        # 创建文本框和滚动条
        self.text = QtWidgets.QTextEdit()
        self.text.setFixedHeight(100)
        input_layout.addWidget(self.text)

        # 添加清空按钮
        clean_btn = QtWidgets.QPushButton("清空")
        clean_btn.clicked.connect(lambda: self.text.clear())
        input_layout.addWidget(clean_btn)

        # 创建说明区域
        help_frame = QtWidgets.QGroupBox("格式说明")
        help_layout = QtWidgets.QVBoxLayout(help_frame)

        keys = ["/tchMaterial", "/syncClassroom"]
        texts = ""
        for i, key in enumerate(keys, 1):
            config = RESOURCE_DICT[key]
            texts += f"{i}. {config['name'][:2]}URL：" + str(config["resources"]["detail"]) + "\n"

        help_text = f"支持的URL格式示例：\n{texts}\n可以直接从浏览器地址复制URL。"
        help_label = QtWidgets.QLabel(help_text)
        help_label.setWordWrap(True)
        help_layout.addWidget(help_label)

        input_layout.addWidget(help_frame)
        self.setLayout(input_layout)

    def get_urls(self) -> list:
        """获取输入的URL列表"""
        text = self.text.toPlainText().strip()
        urls = [url.strip() for url in text.split("\n") if url.strip()] if text else []
        return urls


class DownloadApp(QtWidgets.QMainWindow):
    """主应用窗口"""

    def __init__(self, scale=1.0, os_name=None):
        super().__init__()
        self.frame_names = ["books", "inputs"]
        self.frame_titles = ["教材列表", "手动输入"]
        self.desc_texts = DESCRIBES
        self.download_dir = Path.home() / "Downloads"  # 改为用户目录

        self.scale = scale
        self.os_name = os_name
        width = int(750 * scale)
        height = int(700 * scale)
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)

        # 图形大小
        self.setWindowTitle(self.desc_texts[0])
        self.setGeometry(100, 100, width, height)

        # 设置Icon
        # small_icon_file = base64_to_image(ICON_SMALL, "icon_small.png")
        # large_icon_file = base64_to_image(ICON_LARGE, "icon_large.png")
        # self.setWindowIcon(QtGui.QIcon(large_icon_file))

        self.fonts, default_size = self.setup_fonts()
        self.font_size = int(default_size * min((1.1 + (scale - 1) * 0.3), 1.5))

        self.setup_ui()

    def setup_ui(self):
        """初始化UI: 标题、目录+下载按钮、单选按钮内容区域、进度条"""

        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QtWidgets.QVBoxLayout(main_widget)

        self.setup_title_frame(main_layout)
        self.setup_mode_frame(main_layout)
        self.setup_control_frame(main_layout)

    def setup_fonts(self):
        font_families = {
            "sans_serif": ["Arial", "Helvetica", "Segoe UI", "Roboto"],
            "serif": ["Georgia", "Times New Roman"],
            "monospace": ["Monaco", "Courier New", "Consolas"],
            "kaiti": ["STKaiti", "SimKai", "楷体"],
        }
        default_font = QtGui.QFont()
        default_family = default_font.family()
        default_size = default_font.pointSize()
        available_fonts = QtGui.QFontDatabase.families()

        font_dict = {}
        for key, fonts in font_families.items():
            for font in fonts:
                if font in available_fonts:
                    font_dict[key] = font
                    break
            else:
                font_dict[key] = default_family
        return font_dict, default_size

    def setup_title_frame(self, main_layout):
        # 1. 添加标题和LOGO
        title_frame = QtWidgets.QFrame()
        title_layout = QtWidgets.QVBoxLayout(title_frame)
        main_layout.addWidget(title_frame)

        title_layout.addWidget(QtWidgets.QLabel(LOGO_TEXT))
        slogan_label = QtWidgets.QLabel(self.desc_texts[2])
        title_layout.addWidget(slogan_label)

    def setup_mode_frame(self, main_layout):
        # 3. 模式选择：两个单选按钮
        self.mode_var = self.frame_names[0]  # Default to the first frame name
        mode_frame = QtWidgets.QFrame()  # Create the QFrame without passing the layout
        main_layout.addWidget(mode_frame)  # Add the frame to the main layout
        mode_layout = QtWidgets.QHBoxLayout(mode_frame)

        radio1 = QtWidgets.QRadioButton(self.frame_titles[0])
        radio1.setChecked(True)
        radio1.toggled.connect(self.switch_mode)
        mode_layout.addWidget(radio1)

        radio2 = QtWidgets.QRadioButton(self.frame_titles[1])
        radio2.toggled.connect(self.switch_mode)
        mode_layout.addWidget(radio2)

        # 4. 内容区域，包括两个面板，单选控制
        self.content_frame = QtWidgets.QFrame()  # Create the QFrame without passing the layout
        main_layout.addWidget(self.content_frame)  # Add the frame to the main layout
        self.selector_frame = BookSelectorFrame(
            self.content_frame, self.fonts, self.font_size, self.scale, self.os_name
        )
        self.inputs_frame = InputURLAreaFrame(
            self.content_frame, self.fonts, self.font_size, self.scale, self.os_name
        )

        # 默认显示教材列表面板
        self.selector_frame.show()

    def setup_control_frame(self, main_layout):
        # New: 资源类型选项
        formats_frame = QtWidgets.QFrame()  # Create the QFrame without passing the layout
        main_layout.addWidget(formats_frame)  # Add the frame to the main layout
        formats_layout = QtWidgets.QHBoxLayout(formats_frame)
        formats_layout.addWidget(QtWidgets.QLabel("资源类型"))

        self.formats_vars = {}
        for name, suffix in zip(RESOURCE_NAMES, RESOURCE_FORMATS):
            var = False  # Use a standard boolean variable instead of pyqtSignal
            self.formats_vars[suffix] = var
            value, state = False, "enable"
            if suffix == RESOURCE_FORMATS[0]:
                value = True
            if suffix == RESOURCE_FORMATS[-2]:
                state = "disabled"
            var = value  # Set the value of the variable
            text = f"{name}({suffix})" if name in ["文档", "音频"] else name
            checkbutton = QtWidgets.QCheckBox(text)
            checkbutton.setChecked(value)
            formats_layout.addWidget(checkbutton)

        # 2. 目录+下载按钮
        download_frame = QtWidgets.QFrame()  # Create the QFrame without passing the layout
        main_layout.addWidget(download_frame)  # Add the frame to the main layout
        download_layout = QtWidgets.QHBoxLayout(download_frame)

        # 目录选择
        dir_frame = QtWidgets.QFrame(download_frame)
        dir_layout = QtWidgets.QHBoxLayout(dir_frame)
        dir_layout.addWidget(QtWidgets.QLabel("保存目录："))
        self.dir_var = self.download_dir  # Use a standard string variable
        dir_entry = QtWidgets.QLineEdit()
        dir_entry.setText(str(self.dir_var))  # Convert Path to string
        dir_layout.addWidget(dir_entry)
        dir_button = QtWidgets.QPushButton("选择目录")
        dir_button.clicked.connect(self.choose_directory)
        dir_layout.addWidget(dir_button)

        download_layout.addWidget(dir_frame)

        # 下载按钮
        download_button = QtWidgets.QPushButton("开始下载")
        download_button.clicked.connect(self.start_download)
        download_layout.addWidget(download_button)

        # 底部添加进度条区域
        self.progress_frame = QtWidgets.QFrame()  # Create the QFrame without passing the layout
        main_layout.addWidget(self.progress_frame)  # Add the frame to the main layout
        self.progress_layout = QtWidgets.QVBoxLayout(self.progress_frame)

        # 5. 进度条和标签
        self.progress_label = QtWidgets.QLabel("暂无下载内容")
        self.progress_layout.addWidget(self.progress_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_layout.addWidget(self.progress_bar)

        # 默认隐藏进度条区域
        self.progress_frame.hide()

    def choose_directory(self):
        """选择保存目录"""
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "选择保存目录", str(self.dir_var))
        if directory:
            self.dir_var = directory

    def switch_mode(self):
        """切换模式"""
        if self.mode_var == self.frame_names[0]:
            self.inputs_frame.hide()
            self.selector_frame.show()
        else:
            self.selector_frame.hide()
            self.inputs_frame.show()
            self.inputs_frame.text.setFocus()  # 聚焦在输入框

    def start_download(self):
        """开始下载"""
        # 获取URL列表
        if self.mode_var == self.frame_names[0]:
            urls = self.selector_frame.get_selected_urls()
        else:
            urls = self.inputs_frame.get_urls()

        if not urls:
            QtWidgets.QMessageBox.warning(self, "警告", "请先选择要下载的资源或输入链接")
            return

        suffix_list = [suffix for suffix, var in self.formats_vars.items() if var]
        if len(suffix_list) == 0:
            QtWidgets.QMessageBox.warning(self, "警告", "请至少选择一个下载的资源类型。")
            return

        try:
            # 显示进度条
            self.progress_var.set(0)
            self.progress_label.setText("准备开始下载...")
            self.update()
            result, elapsed_time = self.simple_download(urls, suffix_list)
            self.progress_label.setText("下载完成。")

            if result:
                message = display_results(result, elapsed_time)
            else:
                message = "下载列表为空"
            QtWidgets.QMessageBox.information(self, "下载结果", message)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "错误", f"下载失败：{str(e)}")

    def simple_download(self, urls, suffix_list):
        save_path = self.dir_var
        logging.debug(f"\n共选择 {len(urls)} 项目，将保存到 {save_path} 目录，类型 {suffix_list}")

        # 更新进度显示
        self.progress_label.setText("正在解析URL...")
        base_progress = 10
        self.progress_var.set(base_progress)
        self.update()

        config_urls = parse_urls(urls, suffix_list)
        resource_dict = fetch_all_data(
            config_urls, lambda data: extract_resource_url(data, suffix_list)
        )

        total = len(resource_dict)
        self.progress_label.setText(f"共找到配置链接 {len(config_urls)} 项，资源文件 {total} 项")
        base_progress = 20
        self.progress_var.set(base_progress)
        self.update()

        if total == 0:
            logging.warning(f"\n没有找到资源文件（{'/'.join(suffix_list)}等）。结束下载")
            return None, None

        # 开始下载
        start_time = time.time()

        # 更新进度显示
        self.progress_label.setText(f"开始下载 {total} 项资源...")
        self.update()
        results = download_files_tk(self, resource_dict, save_path, base_progress=base_progress)

        # 更新进度显示
        self.progress_var.set(100)
        self.update()

        elapsed_time = time.time() - start_time
        return results, elapsed_time


def main(theme=None):
    import sys  # Ensure sys is imported
    try:
        # scale, os_name = set_dpi_scale()
        app = QtWidgets.QApplication()  # Pass sys.argv to QApplication
        scale, os_name = 1.0, 'Windows'
        window = DownloadApp(scale, os_name)
        # set_theme(theme=theme, font_scale=scale)
        window.show()
        sys.exit(app.exec())  # Use sys.exit to ensure proper cleanup
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)  # Exit with an error code

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--theme", "-t", default="auto", type=str, choices=["light", "dark", "auto", "raw"]
    )
    args = parser.parse_args()

    # 配置日志
    fmt = "%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s"
    log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format=fmt)
    logging.debug("调试模式已启用")

    main(args.theme) 