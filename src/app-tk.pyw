"""
图形界面版本（tkinter实现）：智慧教育平台资源下载工具
"""

import logging
import time
import tkinter as tk
import tkinter.font as tkFont
from tkinter import filedialog, messagebox, ttk

from tools.downloader import download_files_tk, fetch_all_data
from tools.parser import extract_resource_url, parse_urls
from tools.parser2 import fetch_metadata, gen_url_from_tags, query_metadata
from tools.utils import base64_to_image
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
        width = frame.winfo_width()
    elif event:
        width = event.width
    else:
        width = labels[0].winfo_toplevel().winfo_width()
    wraplength = int(width - delta * scale)

    for label in labels:
        label.configure(wraplength=wraplength)


class BookSelectorFrame(ttk.Frame):
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

        self.pack(fill=tk.BOTH, expand=True)
        # 创建左右两个部分
        self.books_frame = ttk.LabelFrame(self, text=self.frame_names[0], padding=self.padx * 2)
        self.books_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=self.padx)

        self.hierarchy_frame = ttk.LabelFrame(self, text=self.frame_names[1], padding=self.padx * 2)
        self.hierarchy_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=self.padx)

        self.setup_books_frame()
        self.setup_hierarchy_frame()

    def setup_books_frame(self):
        """设置课本部分"""
        # 上半部分：多选框的frame（滚动条）
        checkbox_frame = ttk.Frame(self.books_frame)
        checkbox_frame.pack(fill=tk.BOTH, expand=True)

        # 创建Canvas和Scrollbar
        canvas = tk.Canvas(checkbox_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(checkbox_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        # 绑定Canvas和Scrollbar
        self.scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((self.padx, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=self.scrollbar.set)

        # 设置最大高度
        checkbox_frame.configure(height=self.checkbox_height)  # 设置最大高度
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # 处理鼠标滚轮事件
        canvas.bind_all(
            "<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        )
        # self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        checkbox_frame.bind(
            "<Configure>",
            lambda e: update_labels_wraplength(
                e, [v[2] for v in self.checkbox_list], self.scale, int(60 * self.scale), checkbox_frame
        ))

        # 下半部分：全选和取消全选按钮
        btn_frame = ttk.Frame(self.books_frame)
        btn_frame.pack(side=tk.BOTTOM, padx=self.padx)

        self.select_all_btn = ttk.Button(btn_frame, text="全选", command=self.select_all)
        self.deselect_all_btn = ttk.Button(btn_frame, text="取消全选", command=self.deselect_all)
        self.select_all_btn.pack(side=tk.RIGHT, padx=self.padx)
        self.deselect_all_btn.pack(side=tk.RIGHT, padx=self.padx)
        self.select_all_btn.configure(state=tk.DISABLED)
        self.deselect_all_btn.configure(state=tk.DISABLED)

    def setup_hierarchy_frame(self):
        """设置教材层级部分"""
        # 上半部分：下拉框的frame
        self.combo_frame = ttk.Frame(self.hierarchy_frame)
        self.combo_frame.pack(fill=tk.BOTH)  # , expand=True

        # 下半部分：查询按钮
        query_btn_frame = ttk.Frame(self.hierarchy_frame)
        query_btn_frame.pack(side=tk.BOTTOM, anchor="s")

        self.query_btn = ttk.Button(query_btn_frame, text="查询", command=self.query_data)
        self.query_btn.pack(side=tk.RIGHT)

    def query_data(self):
        """查询数据并更新下拉框"""
        # 获取第一级数据
        if self.hier_dict is None:
            self.hierarchy_frame.configure(text="联网查询教材数据中……")
            self.hier_dict, self.tag_dict, self.id_dict = fetch_metadata(None)

        if self.hier_dict:
            logging.debug(f"hier_dict = {len(self.hier_dict)}")
            self.hierarchy_frame.configure(text="查询完成")
            self.hierarchy_frame.configure(text=self.frame_names[1])
            self.update_frame(0)
        else:
            self.update_frame(-1, -1)
            messagebox.showerror("错误", "获取数据失败，请稍后再试")

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

        frame = ttk.Frame(self.combo_frame)
        frame.pack(fill=tk.X, side=tk.TOP, expand=True, padx=self.padx, pady=self.pady)

        level_count = len(self.level_options) - 1
        label = ttk.Label(frame, text=f"{level_count}. 【{name}】", font=("bold",))
        label.pack(fill=tk.X, expand=True, padx=self.padx * 2)

        option_names = [op[1] for op in options]
        cb = ttk.Combobox(frame, state="readonly", values=option_names, width=10)
        cb.pack(fill=tk.X, expand=True, pady=self.pady)  #
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_combobox_select(index, cb.get()))

        self.combobox_list.append([label, cb, frame])

        if len(option_names) == 0:
            self.hierarchy_frame.configure(text=f"{self.frame_names[1]}: {name} 数据为空")
        else:
            self.hierarchy_frame.configure(text=self.frame_names[1])

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
                w.destroy()
        self.combobox_list = self.combobox_list[:index2]

        self.level_hiers = self.level_hiers[: index2 + 1]
        self.level_options = self.level_options[: index2 + 1]

    def update_checkbox(self, options):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.checkbox_list = []
        self.selected_items = set()
        self.scrollbar.pack_forget()  # 隐藏滚动条
        logging.debug(f"=>>> options = {options}")
        if not options:
            self.select_all_btn.configure(state=tk.DISABLED)
            self.deselect_all_btn.configure(state=tk.DISABLED)
            self.books_frame.configure(text=self.frame_names[0])
            if options is not None and len(options) == 0:
                self.books_frame.configure(text=f"{self.frame_names[0]}: 数据为空")
            return

        width = len(str(len(options)))
        for i, (book_id, book_name) in enumerate(options):
            var = tk.BooleanVar()
            var.set(False)
            frame = ttk.Frame(self.scrollable_frame)
            frame.pack(fill=tk.X, side=tk.TOP, expand=True)
            cb = ttk.Checkbutton(
                frame,
                variable=var,
                command=lambda id=book_id: self.toggle_checkbox_selection(id),
            )
            # 使用label自动换行
            label = ttk.Label(frame, text=f"{i + 1:0{width}d}. {book_name}")
            cb.pack(side=tk.LEFT)
            label.pack(side=tk.LEFT)
            self.checkbox_list.append((var, cb, label))

        if options:
            self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.select_all_btn.configure(state=tk.NORMAL)
            self.deselect_all_btn.configure(state=tk.NORMAL)
            self.books_frame.configure(text=f"{self.frame_names[0]}: 共 {len(options)} 项资源")

    def toggle_checkbox_selection(self, book_id: str):
        """切换选择状态"""
        if book_id in self.selected_items:
            self.selected_items.remove(book_id)
        else:
            self.selected_items.add(book_id)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.configure(text=f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def select_all(self):
        """全选"""
        self.selected_items = set([op[0] for op in self.level_options[-1]])
        for var in self.checkbox_list:
            var[0].set(True)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.configure(text=f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def deselect_all(self):
        """取消全选"""
        self.selected_items = set()
        for var in self.checkbox_list:
            var[0].set(False)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.configure(text=f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def get_selected_urls(self) -> list[str]:
        """获取选中的URL列表"""
        return gen_url_from_tags(list(self.selected_items))


class InputURLAreaFrame(ttk.Frame):
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
        input_frame = ttk.LabelFrame(self, text="输入URL（每行一个）", padding=self.padx * 2)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=self.padx, pady=self.pady)

        # 创建文本框和滚动条
        text_frame = ttk.Frame(input_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=self.pady)

        self.text = tk.Text(
            text_frame, height=5, width=20, font=(self.fonts["sans_serif"], self.font_size)
        )
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 添加清空按钮
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(fill=tk.X, pady=self.pady)
        clean_btn = ttk.Button(
            btn_frame, text="清空", command=lambda: self.text.delete("1.0", tk.END)
        )
        clean_btn.pack(side=tk.RIGHT)

        # 创建说明区域
        help_frame = ttk.LabelFrame(self, text="格式说明", padding=self.padx * 2)
        help_frame.pack(fill=tk.BOTH, expand=True, padx=self.padx, pady=self.pady)

        keys = ["/tchMaterial", "/syncClassroom"]
        texts = ""
        for i, key in enumerate(keys, 1):
            config = RESOURCE_DICT[key]
            texts += f"{i}. {config['name'][:2]}URL：" + str(config["resources"]["detail"]) + "\n"

        help_text = f"支持的URL格式示例：\n{texts}\n可以直接从浏览器地址复制URL。"
        help_label = ttk.Label(
            help_frame, text=help_text, justify=tk.LEFT, font=(self.fonts["kaiti"], self.font_size)
        )
        help_label.pack(fill=tk.X, padx=self.padx, pady=self.pady)
        help_frame.bind(
            "<Configure>", lambda e: update_labels_wraplength(e, [help_label], self.scale)
        )

    def get_urls(self) -> list:
        """获取输入的URL列表"""
        text = self.text.get("1.0", tk.END).strip()
        urls = [url.strip() for url in text.split("\n") if url.strip()] if text else []
        return urls


class DownloadApp(tk.Tk):
    """主应用窗口"""

    def __init__(self, scale=1.0, os_name=None):
        super().__init__()
        self.frame_names = ["books", "inputs"]
        self.frame_titles = ["教材列表", "手动输入"]
        self.desc_texts = DESCRIBES
        self.download_dir = "./downloads"  # 改为用户目录

        self.scale = scale
        self.os_name = os_name
        width = int(750 * scale)
        height = int(700 * scale)
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)

        # 图形大小
        self.title(self.desc_texts[0])
        self.geometry(f"{width}x{height}")
        self.wm_minsize(width=int(width * 0.8), height=int(height * 0.9))
        # self.resizable(False, False)  # Prevent resizing the window

        # 设置主题
        # style = ttk.Style()
        # style.theme_use('')

        # 设置Icon
        small_icon_file = base64_to_image(ICON_SMALL, "icon_small.png")
        large_icon_file = base64_to_image(ICON_LARGE, "icon_large.png")
        small_icon = tk.PhotoImage(file=small_icon_file)
        large_icon = tk.PhotoImage(file=large_icon_file)
        self.iconphoto(False, large_icon, small_icon)

        self.fonts, default_size = self.setup_fonts()
        self.font_size = int(default_size * min((1.1 + (scale - 1) * 0.3), 1.5))

        self.setup_ui()

    def setup_ui(self):
        """初始化UI: 标题、目录+下载按钮、单选按钮、内容区域、进度条"""

        main_frame = ttk.Frame(self)  # padding=self.padx*2
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.setup_title_frame(main_frame)
        self.setup_mode_frame(main_frame)
        self.setup_control_frame(main_frame)

    def setup_fonts(self):
        font_families = {
            "sans_serif": ["Arial", "Helvetica", "Segoe UI", "Roboto"],
            "serif": ["Georgia", "Times New Roman"],
            "monospace": ["Monaco", "Courier New", "Consolas"],
            "kaiti": ["STKaiti", "SimKai", "楷体"],
        }
        default_font = tkFont.nametofont("TkDefaultFont")
        default_family = default_font.actual("family")
        default_size = default_font.actual("size")
        available_fonts = tkFont.families()

        font_dict = {}
        for key, fonts in font_families.items():
            for font in fonts:
                if font in available_fonts:
                    font_dict[key] = font
                    break
            else:
                font_dict[key] = default_family
        return font_dict, default_size

    def setup_title_frame(self, main_frame):
        # 1. 添加标题和LOGO
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            title_frame, text=LOGO_TEXT, anchor=tk.CENTER, font=(self.fonts["monospace"],)
        ).pack(fill=tk.BOTH, expand=True)
        slogan_label = ttk.Label(
            title_frame,
            text=self.desc_texts[2],
            anchor=tk.CENTER,
            font=(self.fonts["kaiti"], self.font_size),
        )
        slogan_label.pack(fill=tk.BOTH, expand=True, pady=self.pady)
        title_frame.bind(
            "<Configure>", lambda e: update_labels_wraplength(e, [slogan_label], self.scale)
        )

    def setup_mode_frame(self, main_frame):
        # 3. 模式选择：两个单选按钮
        self.mode_var = tk.StringVar(value=self.frame_names[0])
        mode_frame = ttk.Frame(main_frame)
        mode_frame.pack(fill=tk.BOTH, expand=True, pady=self.pady)

        radio1 = ttk.Radiobutton(
            mode_frame,
            text=self.frame_titles[0],
            value=self.frame_names[0],
            variable=self.mode_var,
            command=self.switch_mode,
        )

        radio2 = ttk.Radiobutton(
            mode_frame,
            text=self.frame_titles[1],
            value=self.frame_names[1],
            variable=self.mode_var,
            command=self.switch_mode,
        )
        radio1.pack(side=tk.LEFT, fill=tk.X, padx=self.padx * 2)
        radio2.pack(side=tk.LEFT, fill=tk.X, padx=self.padx * 2)

        # 4. 内容区域，包括两个面板，单选控制
        self.content_frame = ttk.Frame(main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        self.selector_frame = BookSelectorFrame(
            self.content_frame, self.fonts, self.font_size, self.scale, self.os_name
        )
        self.inputs_frame = InputURLAreaFrame(
            self.content_frame, self.fonts, self.font_size, self.scale, self.os_name
        )

        # 默认显示教材列表面板
        self.selector_frame.pack(fill=tk.BOTH, expand=True, pady=self.pady * 2)

    def setup_control_frame(self, main_frame):
        # New: 资源类型选项
        formats_frame = ttk.Frame(main_frame)
        formats_frame.pack(fill=tk.X, pady=self.pady)
        ttk.Label(formats_frame, text="资源类型").pack(side=tk.LEFT, padx=self.padx)

        self.formats_vars = {}
        for name, suffix in zip(RESOURCE_NAMES, RESOURCE_FORMATS):
            var = tk.BooleanVar()
            self.formats_vars[suffix] = var
            value, state = False, "enable"
            if suffix == RESOURCE_FORMATS[0]:
                value = True
            if suffix == RESOURCE_FORMATS[-2]:
                state = "disabled"
            var.set(value)
            text = f"{name}({suffix})" if name in ["文档", "音频"] else name
            checkbutton = ttk.Checkbutton(
                formats_frame, text=text, variable=var, onvalue=1, offvalue=0, state=state
            )
            checkbutton.pack(side=tk.LEFT, padx=self.padx)

        # 2. 目录+下载按钮
        download_frame = ttk.Frame(main_frame)
        download_frame.pack(fill=tk.X, pady=self.pady)

        # 目录选择
        dir_frame = ttk.Frame(download_frame)
        dir_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(dir_frame, text="保存目录：").pack(side=tk.LEFT, padx=self.padx)
        self.dir_var = tk.StringVar(value=self.download_dir)
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=self.pady)
        ttk.Button(dir_frame, text="选择目录", command=self.choose_directory).pack(side=tk.LEFT)

        # 下载按钮
        ttk.Button(download_frame, text="开始下载", command=self.start_download).pack(
            side=tk.LEFT, padx=self.padx * 2
        )

        # 底部添加进度条区域
        self.progress_frame = ttk.Frame(main_frame)
        self.progress_frame.pack(fill=tk.X, pady=self.pady)

        # 5. 进度条和标签
        self.progress_var = tk.DoubleVar()
        self.progress_label = ttk.Label(self.progress_frame, text="暂无下载内容")
        self.progress_label.pack(fill=tk.X, padx=self.padx, pady=self.pady)

        self.progress_bar = ttk.Progressbar(
            self.progress_frame, mode="determinate", variable=self.progress_var
        )
        self.progress_bar.pack(fill=tk.X, pady=self.pady)

        # 默认隐藏进度条区域
        # self.progress_frame.pack_forget()

    def choose_directory(self):
        """选择保存目录"""
        directory = filedialog.askdirectory(title="选择保存目录", initialdir=self.dir_var.get())
        if directory:
            self.dir_var.set(directory)

    def switch_mode(self):
        """切换模式"""
        if self.mode_var.get() == self.frame_names[0]:
            self.inputs_frame.pack_forget()
            self.selector_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.selector_frame.pack_forget()
            self.inputs_frame.pack(fill=tk.BOTH, expand=True)
            self.inputs_frame.text.focus_set()  # 聚焦在输入框

    def start_download(self):
        """开始下载"""
        # 获取URL列表
        if self.mode_var.get() == self.frame_names[0]:
            urls = self.selector_frame.get_selected_urls()
        else:
            urls = self.inputs_frame.get_urls()

        if not urls:
            messagebox.showwarning("警告", "请先选择要下载的资源或输入链接")
            return

        suffix_list = [suffix for suffix, var in self.formats_vars.items() if var.get()]
        if len(suffix_list) == 0:
            messagebox.showwarning("警告", "请至少选择一个下载的资源类型。")
            return

        # 确认下载弹窗
        # save_dir = self.dir_var.get()
        # if not messagebox.askyesno("确认下载", f"将下载 {len(urls)} 个资源到目录：\n{save_dir}\n\n是否继续？"):
        #     return

        try:
            # 显示进度条
            self.progress_var.set(0)
            self.progress_label.configure(text="准备开始下载...")
            self.update()
            result, elapsed_time = self.simple_download(urls, suffix_list)
            self.progress_label.configure(text="下载完成。")

            if result:
                message = display_results(result, elapsed_time)
            else:
                message = "下载列表为空"
            messagebox.showinfo("下载结果", message)

        except Exception as e:
            messagebox.showerror("错误", f"下载失败：{str(e)}")

    def simple_download(self, urls, suffix_list):
        save_path = self.dir_var.get()
        logging.debug(f"\n共选择 {len(urls)} 项目，将保存到 {save_path} 目录，类型 {suffix_list}")

        # 更新进度显示
        self.progress_label.configure(text="正在解析URL...")
        base_progress = 10
        self.progress_var.set(base_progress)
        self.update()

        config_urls = parse_urls(urls, suffix_list)
        resource_dict = fetch_all_data(
            config_urls, lambda data: extract_resource_url(data, suffix_list)
        )

        total = len(resource_dict)
        self.progress_label.configure(
            text=f"共找到配置链接 {len(config_urls)} 项，资源文件 {total} 项"
        )
        base_progress = 20
        self.progress_var.set(base_progress)
        self.update()

        if total == 0:
            logging.warning(f"\n没有找到资源文件（{'/'.join(suffix_list)}等）。结束下载")
            return None, None

        # 开始下载
        start_time = time.time()

        # 更新进度显示
        self.progress_label.configure(text=f"开始下载 {total} 项资源...")
        self.update()
        results = download_files_tk(self, resource_dict, save_path, base_progress=base_progress)

        # 更新进度显示
        self.progress_var.set(100)
        self.update()

        elapsed_time = time.time() - start_time
        return results, elapsed_time


def set_dpi_scale():
    import ctypes
    import platform

    scale = 1.0
    os_name = platform.system()
    if os_name == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ScaleFactor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
        scale = ScaleFactor / 100.0
    return scale, os_name


def main(theme=None):
    scale, os_name = set_dpi_scale()
    app = DownloadApp(scale, os_name)
    # set_theme(theme=theme, font_scale=scale)
    app.eval("tk::PlaceWindow . center")
    app.mainloop()


if __name__ == "__main__":
    main()
