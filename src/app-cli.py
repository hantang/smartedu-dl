"""
命令行版本：智慧教育平台资源下载工具
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import click
from rich.console import Console
from rich.progress import BarColumn, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.progress import Progress
from rich.table import Table

from tools.downloader import download_files, fetch_all_data
from tools.logo import DESCRIBES, LOGO_TEXT2
from tools.parser import extract_resource_url, parse_urls, validate_url
from tools.parser2 import fetch_metadata, gen_url_from_tags, query_metadata


DEFAULT_URLS = []
DATA_PATH = None
DEFAULT_PATH = "./downloads"
EXIT_KEY = "exit"
ZERO_KEY = "0"
FIRST_KEY = "1"
ALL_KEY = "a"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def display_welcome(is_interactive=False):
    """显示欢迎信息"""
    if is_interactive:
        click.clear()
        click.echo(LOGO_TEXT2)
    click.secho(f"=== {DESCRIBES[0]} ===", fg="blue", bold=True)
    click.echo(f"> {DESCRIBES[1]}")
    click.echo(f"> {DESCRIBES[2]}\n")


def parse_range(range_str: str, max_num: int, min_num: int = 1) -> list:
    """解析范围表达式，如 "1-3,5,7-9" """
    range_str = range_str.strip().lower()
    if range_str in ["a", "all"]:
        return list(range(min_num, max_num + 1))

    result = set()
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part and not part.startswith("-"):
            start, end = map(str.strip, part.split("-"))
            if not (start.isdigit() and end.isdigit()):
                continue
            start, end = int(start), int(end)
            start = max(start, min_num)
            end = min(end, max_num)
            if min_num <= start <= end <= max_num:
                result.update(range(start, end + 1))
        else:
            if not part.isdigit():
                continue
            num = int(part)
            if min_num <= num <= max_num:
                result.add(num)
    return sorted(list(result))


def validate_save_path(path_str: str) -> Tuple[bool, str]:
    """验证保存路径"""
    try:
        path = Path(path_str).resolve()
        logging.debug(f"mkdir {path}")
        path.mkdir(parents=True, exist_ok=True)
        return True, str(path)
    except Exception:
        return False, None


def display_entries(data: list, title: str = "URL列表", title2: str = None):
    """显示URL列表"""
    width = len(str(len(data)))
    if title2:
        click.secho(f"\n{title}：", bold=True)
        click.secho(" " * (width + 2) + f"【{title2}】", fg="yellow")
    else:
        click.secho(f"\n{title}：", fg="yellow")

    for i, value in enumerate(data, 1):
        if isinstance(value, str):
            click.echo(f"{click.style(f'[{i:>{width}d}]', bold=True, fg='blue')} {value}")
        else:
            v1, v2 = value
            click.echo(f"{click.style(f'[{v1}]', bold=True, fg='blue')} {v2}")


def display_results(console: Console, results: list, elapsed_time: float):
    """展示下载结果统计"""
    # 创建总体统计表格
    summary_table = Table(title="下载统计", show_header=False, title_style="bold yellow")
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count

    summary_table.add_row("总计文件", str(len(results)))
    summary_table.add_row("成功下载", f"[green]{success_count}[/green]")
    summary_table.add_row("下载失败", f"[red]{failed_count}[/red]")
    summary_table.add_row("总计用时", f"{elapsed_time:.2f}秒")

    console.print("\n")
    console.print(summary_table)

    # 创建详细结果表格
    if results:
        result_table = Table(title="\n下载详情", title_style="bold yellow")
        result_table.add_column("序号", justify="right")
        result_table.add_column("URL", justify="left", no_wrap=False)
        result_table.add_column("状态", justify="center")
        result_table.add_column("存储", justify="left", no_wrap=False)

        for i, res in enumerate(results, 1):
            # status_style = "green" if res["status"] == "success" else "red"
            status = (
                f"[green]成功（{res['code']}）[/green]"
                if res["status"] == "success"
                else f"[red]失败（{res['code']}）[/red]"
            )
            file_path = res.get("file", "---")
            url = res.get("raw", res["url"])
            result_table.add_row(str(i), url, status, file_path)
        console.print(result_table)


def display_stats(console: Console, resource_dict: dict):
    suffix_stats = {}
    for url, [name, raw_url] in resource_dict.items():
        suffix = name.split(".")[-1]
        if suffix not in suffix_stats:
            suffix_stats[suffix] = 0
        suffix_stats[suffix] += 1
    suffix_stats = sorted(suffix_stats.items(), key=lambda x: x[1], reverse=True)

    result_table = Table(title="\n待下载资源", title_style="bold yellow")
    result_table.add_column("序号", justify="right")
    result_table.add_column("类型", justify="left")
    result_table.add_column("数量", justify="right")
    for i, (suffix, count) in enumerate(suffix_stats, 1):
        result_table.add_row(str(i), suffix, str(count))
    console.print(result_table)


def preprocess(list_file, urls):
    # 获取预定义URL
    predefined_urls = []
    if list_file:
        try:
            with open(list_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        more_urls = [url.strip() for url in line.split(",") if url.strip()]
                        predefined_urls.extend(more_urls)
        except Exception as e:
            logger.error(f"读取文件失败: {list_file}, error={e}", exc_info=True)

    if urls:
        predefined_urls.extend(url.strip() for url in urls.split(",") if url.strip())
    urls = [url for url in predefined_urls if validate_url(url)]
    return urls


def simple_download(urls, save_path, formats):
    click.echo(
        f"\n共选择 {click.style(str(len(urls)), fg='yellow')} 项资源，"
        f"将保存到目录【{click.style(str(save_path), fg='yellow')} 】"
    )

    config_urls = parse_urls(urls, formats)
    resource_dict = fetch_all_data(config_urls, lambda data: extract_resource_url(data, formats))
    total = len(resource_dict)

    click.echo(
        f"\n输入的有效链接共 {click.style(str(len(urls)), fg='yellow')} 个；"
        f"\n解析得配置链接共 {click.style(str(len(config_urls)), fg='yellow')} 个；"
        f"\n最终的资源文件共 {click.style(str(total), fg='yellow')} 个。"
    )
    for u in config_urls:
        logging.info(u)
    if total == 0:
        click.echo("\n没有找到资源文件（PDF/MP3等）。结束下载")
        return

    console = Console()
    display_stats(console, resource_dict)

    # 开始下载
    start_time = time.time()
    click.echo("\n开始下载文件...")

    # 下载文件
    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
    ) as progress:
        download_task = progress.add_task("正在下载文件...", total=total)
        results = download_files(resource_dict, save_path)
        progress.update(download_task, completed=total)

    # 显示统计信息
    elapsed_time = time.time() - start_time
    display_results(console, results, elapsed_time)


def _interactive_mode1(hier_dict, tag_dict, id_dict, retry=3):
    def _query(key):
        # 查询下一个下拉框数据
        current_hier_dict = level_hiers[-1]
        level, name, options = query_metadata(key, current_hier_dict, tag_dict, id_dict)
        level_records[-1][2] = name
        return level, name, options

    level_hiers = [hier_dict]
    level_options = [()]
    level_records = [[hier_dict["next"][0], "", ""]]  # (key, option, name)
    options = []
    urls_to_process = []
    flag = True
    while flag:
        last_name = level_records[-2][2] if len(level_records) > 1 else ""
        selected_key, selected_option = level_records[-1][:2]
        level, name, options = _query(selected_key)

        if len(options) == 0:
            note = f"【{last_name}】为“{selected_option}”"
            click.secho(f"\n当前选择的{note}没有候选，请重选", fg="red")
            count = 0
            # 只有单一选项且候选为空都返回
            while len(level_options) > 1 and len(level_options[-1]) <= 1:
                count += 1
                for v in [level_hiers, level_options, level_records]:
                    v.pop()
            if len(level_options) > 1:
                count += 1
                for v in [level_hiers, level_options, level_records]:
                    v.pop()

            click.echo(f"将回退{count}级到【{level_records[-1][2]}】")
            continue
        elif level == -1:
            break

        step = len(level_options)
        note = "，输入0返回上一级" if step > 1 else ""
        note_title = f"{step}. 请选择以下{last_name}某项（共{len(options)}项{note}）"
        option_names = [op[1] for op in options]
        for i in range(retry):
            display_entries(option_names, note_title, name)
            selected_index = click.prompt("请选择", default=FIRST_KEY, show_default=True)
            selected_index = selected_index.strip().lower()

            if selected_index == EXIT_KEY:
                click.secho(f"输入为「{EXIT_KEY}」，退出当前模式", fg="red")
                return []

            if step > 1 and selected_index == ZERO_KEY:
                click.secho(f"输入为「{ZERO_KEY}」，返回上级菜单", fg="blue")
                for v in [level_hiers, level_options, level_records]:
                    v.pop()
                break

            if selected_index.isdigit() and 1 <= int(selected_index) <= len(options):
                # 更新到下一级
                level_hiers.append(level_hiers[-1][selected_key])
                level_options.append(options)
                level_records.append(options[int(selected_index) - 1] + [""])
                break
            else:
                click.secho(f"输入不合法，请重新输入（第{i + 1}/{retry}次）", fg="red")
        else:
            logging.debug("错误次数过多，重置")
            options = []
            flag = False

    if options:
        name2 = name if name else "课本"
        selected_option = level_records[-1][1]
        option_names = [op[1] for op in options]
        note_title = f"当前选择的【{selected_option}】共{len(options)}项，如下"
        display_entries(option_names, note_title, name2)
        urls_to_process = gen_url_from_tags([cid for cid, _ in options])
    return urls_to_process


def _interactive_mode2(retry=3):
    for i in range(retry):
        note = click.style("「smartedu.cn」", fg="blue", bold=True)
        click.echo(f"\n请输入包含{note}资源的URL（逗号分隔）：")
        input_urls = click.prompt("")
        input_urls = input_urls.strip().lower()
        if input_urls == EXIT_KEY:  # 退出
            return []

        urls_to_process = [url.strip() for url in input_urls.split(",") if validate_url(url)]
        if urls_to_process:
            display_entries(urls_to_process, "已输入列表", "有效URL")
            break
        click.secho(f"未输入有效URL，请重新输入（第{i + 1}/{retry}次）", fg="red")
    return urls_to_process


def _interactive_filter(urls_to_process, retry=3):
    selected_urls = []
    for i in range(retry):
        note = "（输入序号或者序号范围，如: 1-3,5,7-9；默认全部）"
        click.echo(f"\n请选择以上候选中需下载项：\n{note}")
        range_input = click.prompt("请输入", default=ALL_KEY.upper(), show_default=True)
        if range_input == EXIT_KEY:
            click.secho(f"输入为「{EXIT_KEY}」，退出当前模式", fg="red")
            return []

        selected_indices = parse_range(range_input, len(urls_to_process))
        if selected_indices:
            selected_urls = [urls_to_process[i - 1] for i in selected_indices]
            break
        click.secho(f"无效的选择，请重新输入（第{i + 1}/{retry}次）", fg="red")

    resource_urls = []
    for url in selected_urls:
        if url.startswith("http"):
            resource_urls.append(url)
    return selected_urls


def _interactive_path(save_path, retry=3):
    for i in range(retry):
        click.echo(f"\n设置保存路径: （默认路径={save_path}）")
        if click.confirm("是否使用默认路径?", default=True):
            break

        save_path = click.prompt("请输入新的保存路径")
        is_valid, validated_path = validate_save_path(save_path)
        if is_valid:
            save_path = validated_path
            break
        click.secho(f"无效的路径：【{save_path}】，请重新输入（第{i + 1}/{retry}次）", fg="red")
    return save_path


def interactive_download(default_output: str, audio: bool):
    """交互式下载流程"""

    hier_dict, tag_dict, id_dict = None, None, None
    mode_options = [
        ["1", "查询教材列表"],
        ["2", "手动输入URL"],
        [ZERO_KEY, f"退出（或{EXIT_KEY}）"],
    ]
    while True:
        note_title = "请选择下载模式（输入数字序号）"
        display_entries(mode_options, note_title)

        choice_values = [idx for idx, _ in mode_options] + [EXIT_KEY]
        choice = click.prompt("请选择", type=click.Choice(choice_values), show_choices=True)
        choice = choice.strip().lower()

        if choice in choice_values[2:]:
            click.echo("\n退出程序")
            sys.exit(0)

        # 获取URL列表
        urls_to_process = []
        if choice == choice_values[0]:
            if hier_dict is None:
                click.echo("\n联网查询教材数据中……")
                data_dir = DATA_PATH
                hier_dict, tag_dict, id_dict = fetch_metadata(data_dir)
            if hier_dict is None:
                click.secho("获取数据失败，请稍后再试", fg="red")
                continue
            urls_to_process = _interactive_mode1(hier_dict, tag_dict, id_dict)
        elif choice == choice_values[1]:
            urls_to_process = _interactive_mode2()

        if not urls_to_process:
            continue

        # 确认下载URL
        resource_urls = _interactive_filter(urls_to_process)
        if not resource_urls:
            click.secho("没有找到可下载的有效URL", fg="red")
            continue
        # 确认保存路径
        save_path = _interactive_path(default_output)

        # 开始下载
        simple_download(resource_urls, save_path, audio)

        # 询问是否继续
        if not click.confirm("\n是否继续下载?", default=True, show_default=True):
            click.echo("\n结束下载")
            break


@click.command()
@click.help_option("-h", "--help")
@click.option("--debug", "-d", is_flag=True, help="启用调试模式")
@click.option("--interactive", "-i", is_flag=True, help="交互模式（默认）")
@click.option("--formats", "-t", help="下载资源类型，逗号分隔")
@click.option("--urls", "-u", help="URL路径列表，逗号分隔")
@click.option("--list_file", "-f", type=click.Path(exists=True), help="包含URL的文件")
@click.option("--output", "-o", type=click.Path(), default=DEFAULT_PATH, help="下载文件保存目录")
def main(
        debug: bool,
        interactive: bool,
        formats: Optional[str],
        urls: Optional[str],
        list_file: Optional[str],
        output: str,
):
    # 如果是请求帮助信息，不需要显示欢迎信息
    if any(arg in sys.argv[1:] for arg in ["-h", "--help"]):
        return

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("调试模式已启用")

    mode = (urls or list_file) and (not interactive)
    display_welcome(not mode)
    if formats:
        formats = formats.split(",")
    else:
        formats = ["pdf"]
    logging.debug(f"formats = {formats}")

    try:
        if mode:
            # 非交互模式，直接下载预定义URL
            predefined_urls = preprocess(list_file, urls)
            if not predefined_urls:
                logger.error("没有提供有效的URL")
                sys.exit(1)
            simple_download(predefined_urls, output, formats)
        else:
            # 默认改成交互模式
            interactive_download(output, formats)
            # logger.warning("请使用-u/-f提供URL列表，或使用-i进行交互")

    except Exception as e:
        logger.error(f"程序执行出错, error={e}", exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n程序已终止")
        sys.exit(0)


if __name__ == "__main__":
    main()
