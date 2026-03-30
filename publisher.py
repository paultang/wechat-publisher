#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号草稿助手 - WeChat Official Account Draft Helper
基于微信公众号 API，实现文章自动创建草稿功能

注意：本工具只创建草稿，不自动发布。用户需要手动在公众号后台发布。

Usage:
    python publisher.py --appid "YOUR_APPID" --secret "YOUR_SECRET" --article article.md
    python publisher.py --appid "YOUR_APPID" --secret "YOUR_SECRET" --title "标题" --content "内容"

Example:
    python publisher.py --appid "wx36ba9f59df0d6313" --secret "ae71bf50f7217042e639b44fb57d5529" \
        --article ml-article.md --author "昌哥" --no-cover
"""

import argparse
import base64
import json
import os
import sys
import tempfile
from datetime import datetime
from typing import Optional

import requests


class WeChatPublisher:
    """
    微信公众号草稿助手
    
    功能：
    - 获取 Access Token
    - 上传封面图片
    - 创建草稿到草稿箱
    - Markdown 转微信 HTML
    
    注意：只创建草稿，不自动发布
    """
    
    def __init__(self, appid: str, secret: str):
        """
        初始化发布助手
        
        Args:
            appid: 微信公众号 AppID
            secret: 微信公众号 AppSecret
        """
        self.appid = appid
        self.secret = secret
        self.access_token: Optional[str] = None
        self.base_url = "https://api.weixin.qq.com/cgi-bin"
    
    def get_access_token(self) -> Optional[str]:
        """
        获取微信公众号 Access Token
        
        Returns:
            access_token 字符串，失败返回 None
        """
        print("🔑 正在获取 access_token...")
        
        url = f"{self.base_url}/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.secret
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if "access_token" in data:
                self.access_token = data["access_token"]
                expires_in = data.get("expires_in", 7200)
                print(f"✅ access_token 获取成功（有效期 {expires_in//60} 分钟）")
                return self.access_token
            else:
                error_code = data.get("errcode", "Unknown")
                error_msg = data.get("errmsg", "Unknown error")
                print(f"❌ access_token 获取失败：{error_code} - {error_msg}")
                return None
                
        except requests.RequestException as e:
            print(f"❌ 网络请求失败：{e}")
            return None
        except Exception as e:
            print(f"❌ 未知错误：{e}")
            return None
    
    def upload_draft(self, title: str, content: str, author: str = None, 
                     digest: str = "", thumb_media_id: str = None) -> Optional[str]:
        """
        上传文章到草稿箱
        
        Args:
            title: 文章标题（≤64 字）
            content: 文章内容（HTML 格式，微信内联样式）
            author: 作者名
            digest: 摘要（≤120 字，默认空字符串）
            thumb_media_id: 封面图片 media_id
            
        Returns:
            media_id: 上传成功返回 media_id，失败返回 None
        """
        if not self.access_token:
            print("❌ 请先获取 access_token")
            return None
        
        print(f"📝 正在上传草稿：{title}")
        
        url = f"{self.base_url}/draft/add?access_token={self.access_token}"
        
        # 构建文章数据（digest 限制 120 字，title 限制 64 字）
        safe_title = title[:64] if len(title) > 64 else title
        # digest 可以为空，避免超限
        safe_digest = digest[:120] if digest and len(digest) > 120 else (digest or "")
        
        articles = {
            "articles": [
                {
                    "title": safe_title,
                    "author": author or "LucianaiB",
                    "digest": safe_digest,
                    "content": content,
                    "content_source_url": "",
                    "thumb_media_id": thumb_media_id,  # 必须提供有效的 media_id
                    "show_cover_pic": 1,  # 显示封面图
                    "need_open_comment": 0,  # 关闭评论
                    "only_fans_can_comment": 0  # 所有人可评论
                }
            ]
        }
        
        try:
            # 使用 json.dumps 确保中文正确编码（ensure_ascii=False）
            import json
            response = requests.post(
                url, 
                data=json.dumps(articles, ensure_ascii=False).encode('utf-8'),
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=30
            )
            data = response.json()
            
            # 微信草稿箱 API 成功时返回 media_id，不一定有 errcode
            if data.get("media_id"):
                media_id = data.get("media_id")
                print(f"✅ 草稿上传成功！media_id: {media_id}")
                return media_id
            elif data.get("errcode") == 0:
                media_id = data.get("media_id")
                print(f"✅ 草稿上传成功！media_id: {media_id}")
                return media_id
            else:
                error_code = data.get("errcode", "Unknown")
                error_msg = data.get("errmsg", "Unknown error")
                print(f"❌ 草稿上传失败：{error_code} - {error_msg}")
                
                # 封面裁剪失败时，尝试上传默认封面
                if error_code == 53402 and not thumb_media_id:
                    print("💡 尝试上传默认封面后重试...")
                    default_media_id = self.upload_default_cover()
                    if default_media_id:
                        articles["articles"][0]["thumb_media_id"] = default_media_id
                        return self.upload_draft(title, content, author, digest, default_media_id)
                
                # 常见错误处理
                if error_code == 40001:
                    print("💡 提示：AppSecret 可能不正确")
                elif error_code == 40014:
                    print("💡 提示：access_token 已过期，请重新获取")
                elif error_code == 45009:
                    print("💡 提示：API 调用频率超限，请稍后再试")
                elif error_code == 53402:
                    print("💡 提示：封面裁剪失败，请提供有效的封面图片")
                
                return None
                
        except Exception as e:
            print(f"❌ 请求失败：{e}")
            return None
    
    # 注意：publish_article 方法已移除
    # 原因：freepublish/submit 接口需要群发权限，个人订阅号默认不支持
    # 用户需要手动在微信公众号后台发布草稿
    
    def upload_image(self, image_path: str) -> Optional[str]:
        """
        上传封面图片（使用 material/add_material 接口获取 media_id）
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            media_id: 上传成功返回 media_id，失败返回 None
        """
        if not self.access_token:
            print("❌ 请先获取 access_token")
            return None
        
        print(f"🖼️ 正在上传封面图片：{image_path}")
        
        # 使用 material/add_material 接口获取 media_id（草稿箱需要）
        url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={self.access_token}&type=image"
        
        try:
            with open(image_path, 'rb') as f:
                files = {"media": f}
                response = requests.post(url, files=files, timeout=30)
                data = response.json()
            
            if "media_id" in data:
                media_id = data["media_id"]
                print(f"✅ 封面图片上传成功！media_id: {media_id}")
                return media_id
            else:
                error_code = data.get("errcode", "Unknown")
                error_msg = data.get("errmsg", "Unknown error")
                print(f"❌ 封面图片上传失败：{error_code} - {error_msg}")
                return None
                
        except Exception as e:
            print(f"❌ 请求失败：{e}")
            return None
    
    def delete_draft(self, media_id: str) -> bool:
        """
        删除草稿
        
        Args:
            media_id: 草稿的 media_id
            
        Returns:
            bool: 删除成功返回 True，失败返回 False
        """
        if not self.access_token:
            print("❌ 请先获取 access_token")
            return False
        
        print(f"🗑️ 正在删除草稿：{media_id}")
        
        url = f"{self.base_url}/draft/delete?access_token={self.access_token}"
        
        data = {"media_id": media_id}
        
        try:
            response = requests.post(url, json=data, timeout=30)
            result = response.json()
            
            if result.get("errcode") == 0:
                print(f"✅ 草稿删除成功")
                return True
            else:
                error_code = result.get("errcode", "Unknown")
                error_msg = result.get("errmsg", "Unknown error")
                print(f"❌ 草稿删除失败：{error_code} - {error_msg}")
                return False
                
        except Exception as e:
            print(f"❌ 请求失败：{e}")
            return False
    
    def get_article_url(self, article_id: str) -> str:
        """
        生成文章链接
        
        Args:
            article_id: 文章 ID
            
        Returns:
            str: 文章链接
        """
        # 微信公众号文章链接格式
        return f"https://mp.weixin.qq.com/s/{article_id}"
    
    def publish_from_markdown(self, markdown_file: str, title: str = None, 
                              author: str = "LucianaiB", thumb_media_id: str = None) -> Optional[str]:
        """
        从 Markdown 文件创建草稿
        
        流程：
        1. 读取 Markdown 文件
        2. 提取标题（如果没有提供）
        3. Markdown 转 HTML
        4. 上传草稿到草稿箱
        
        Args:
            markdown_file: Markdown 文件路径
            title: 文章标题（可选，默认从文件提取）
            author: 作者名
            thumb_media_id: 封面图片 media_id（可选）
            
        Returns:
            media_id: 草稿创建成功返回 media_id，失败返回 None
        """
        print(f"📄 正在读取 Markdown 文件：{markdown_file}")
        
        # 检查文件是否存在
        if not os.path.exists(markdown_file):
            print(f"❌ 文件不存在：{markdown_file}")
            return None
        
        # 读取 Markdown 内容
        with open(markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 如果没有指定标题，从文件内容提取
        if not title:
            for line in content.split('\n'):
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
            if not title:
                title = os.path.basename(markdown_file).replace('.md', '')
        
        print(f"📝 文章标题：{title}")
        
        # Markdown 转 HTML（简单转换）
        html_content = self._markdown_to_html(content)
        
        # 获取 access_token
        self.get_access_token()
        if not self.access_token:
            return None
        
        # 上传草稿（digest 限制 120 字，直接传空字符串避免超限）
        media_id = self.upload_draft(
            title=title,
            content=html_content,
            author=author,
            digest="",  # 空摘要，避免超限
            thumb_media_id=thumb_media_id
        )
        
        if media_id:
            print(f"\n✅ 文章已保存到草稿箱！")
            print(f"   Media ID: {media_id}")
            print(f"\n💡 提示：请前往微信公众号后台 (https://mp.weixin.qq.com/) 查看并发布。\n")
            return media_id
        
        return None
    
    def _markdown_to_html(self, markdown: str) -> str:
        """
        核心渲染函数：14px 苹果细圆体 + MacOS 无阴影代码块 (物理隔离法)
        针对年轻受众优化的最终对齐版本，保持代码缩进并支持横向滑动
        """
        lines = markdown.split('\n')
        html_parts = []
        in_code_block = False
        code_content = []

        # 【样式定义】14px 苹果细圆体正文
        body_style = (
            'font-family: "PingFang SC", "STHeiti", "Microsoft YaHei", sans-serif; '
            'font-size: 14px; color: #333333; line-height: 1.7; letter-spacing: 0.5px; '
            'margin: 12px 0; text-align: justify; -webkit-font-smoothing: antialiased;'
        )

        for line in lines:
            raw_line = line 
            stripped_line = line.strip()

            # 1. 处理代码块 (拦截 ```)
            if stripped_line.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    continue
                else:
                    in_code_block = False
                    formatted_rows = []
                    for code_row in code_content:
                        safe_row = code_row.replace('<', '&lt;').replace('>', '&gt;').replace(' ', '&nbsp;')
                        row_html = (
                            f'<p style="margin: 0; padding: 0 20px; white-space: nowrap !important; line-height: 1.8;">'
                            f'<code style="font-family: Menlo, Monaco, monospace; font-size: 12px; color: #abb2bf;">{safe_row}</code>'
                            f'</p>'
                        )
                        formatted_rows.append(row_html)
                    
                    code_text = ''.join(formatted_rows)
                    macos_widget = (
                        '<section style="margin: 20px 0; border-radius: 8px; overflow: hidden; background: #282c34; border: 1px solid #1b1d23;">'
                        '<section style="display: flex; padding: 12px; background: #21252b;">'
                        '<svg width="54" height="12"><circle cx="6" cy="6" r="6" fill="#ff5f56"/><circle cx="26" cy="6" r="6" fill="#ffbd2e"/><circle cx="46" cy="6" r="6" fill="#27c93f"/></svg>'
                        '</section>'
                        f'<section style="padding: 10px 0 10px 0; overflow-x: auto; -webkit-overflow-scrolling: touch;">'
                        f'{code_text}'
                        '</section></section>'
                    )
                    html_parts.append(macos_widget)
                    code_content = []
                    continue

            # 2. 收集代码块内部内容
            if in_code_block:
                code_content.append(raw_line)
                continue

            # 3. 处理普通 Markdown 逻辑
            if not stripped_line:
                continue

            if stripped_line.startswith('# '):
                title = stripped_line[2:]
                html_parts.append(f'<h2 style="font-family: \'PingFang SC\'; font-size: 18px; margin: 24px 0 12px; color: #000; font-weight: bold;">{title}</h2>')
            elif stripped_line.startswith('## '):
                subtitle = stripped_line[3:]
                html_parts.append(f'<h3 style="font-family: \'PingFang SC\'; font-size: 16px; margin: 20px 0 10px; color: #000; font-weight: bold;">{subtitle}</h3>')
            elif stripped_line.startswith('> '):
                quote = stripped_line[2:]
                html_parts.append(f'<section style="border-left:4px solid #ddd; padding-left:12px; margin:12px 0; color:#666; font-style:italic; font-size:14px;">{quote}</section>')
            elif stripped_line.startswith('- ') or stripped_line.startswith('* '):
                item = stripped_line[2:]
                html_parts.append(f'<section style="{body_style}">• {item}</section>')
            else:
                processed_line = stripped_line.replace('**', '<strong>', 1).replace('**', '</strong>', 1)
                html_parts.append(f'<section style="{body_style}">{processed_line}</section>')

        return '\n'.join(html_parts)
        
    def upload_default_cover(self) -> Optional[str]:
        """
        上传默认封面图（900x500 像素，微信要求最小 200x200）
        
        策略：
        1. 优先从 picsum.photos 获取免费占位图
        2. 失败时使用本地生成的 BMP 图片
        
        Returns:
            media_id: 上传成功返回 media_id，失败返回 None
        """
        # 方案 1：从 picsum.photos 获取免费占位图
        try:
            response = requests.get("https://picsum.photos/900/500", timeout=30)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                    f.write(response.content)
                    temp_path = f.name
                
                media_id = self.upload_image(temp_path)
                os.unlink(temp_path)
                return media_id
        except Exception as e:
            print(f"⚠️  在线获取封面失败：{e}，使用本地生成...")
        
        # 方案 2：本地生成简单的 BMP 图片（900x500，蓝色）
        try:
            width, height = 900, 500
            bmp_header = self._create_bmp_header(width, height)
            blue_pixel = bytes([0x80, 0x40, 0x20])  # 深蓝色 (BGR)
            row_size = (width * 3 + 3) & ~3  # 行对齐
            padding = bytes([0x00] * (row_size - width * 3))
            row = blue_pixel * width + padding
            
            with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as f:
                f.write(bmp_header)
                for _ in range(height):
                    f.write(row)
                temp_path = f.name
            
            media_id = self.upload_image(temp_path)
            os.unlink(temp_path)
            return media_id
        except Exception as e:
            print(f"❌ 默认封面生成失败：{e}")
            return None
    
    def _create_bmp_header(self, width: int, height: int) -> bytes:
        """创建 BMP 文件头"""
        row_size = (width * 3 + 3) & ~3
        image_size = row_size * height
        file_size = 54 + image_size
        
        return bytes([
            0x42, 0x4D,  # BM
            file_size & 0xFF, (file_size >> 8) & 0xFF, (file_size >> 16) & 0xFF, (file_size >> 24) & 0xFF,
            0x00, 0x00, 0x00, 0x00,  # 保留
            0x36, 0x00, 0x00, 0x00,  # 数据偏移
            0x28, 0x00, 0x00, 0x00,  # 信息头大小
            width & 0xFF, (width >> 8) & 0xFF, (width >> 16) & 0xFF, (width >> 24) & 0xFF,
            height & 0xFF, (height >> 8) & 0xFF, (height >> 16) & 0xFF, (height >> 24) & 0xFF,
            0x01, 0x00,  # 平面数
            0x18, 0x00,  # 位数 (24)
            0x00, 0x00, 0x00, 0x00,  # 压缩
            image_size & 0xFF, (image_size >> 8) & 0xFF, (image_size >> 16) & 0xFF, (image_size >> 24) & 0xFF,
            0x13, 0x0B, 0x00, 0x00,  # 水平分辨率
            0x13, 0x0B, 0x00, 0x00,  # 垂直分辨率
            0x00, 0x00, 0x00, 0x00,  # 颜色数
            0x00, 0x00, 0x00, 0x00,  # 重要颜色
        ])
    
    def print_config(self):
        """打印配置信息"""
        print("\n" + "=" * 60)
        print("📱 微信公众号发布助手")
        print("=" * 60)
        print(f"AppID: {self.appid[:10]}...{self.appid[-6:]}")
        print(f"Secret: {self.secret[:6]}...{self.secret[-6:]}")
        print("=" * 60 + "\n")


def main():
    """
    主函数 - 解析命令行参数并执行相应操作
    
    支持两种模式：
    1. Markdown 文件模式：--article article.md
    2. 直接输入模式：--title "标题" --content "内容"
    """
    parser = argparse.ArgumentParser(
        description='微信公众号草稿助手 - 一键创建草稿到草稿箱',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python publisher.py --appid "YOUR_APPID" --secret "YOUR_SECRET" --article article.md --author "昌哥" --no-cover
  python publisher.py --appid "YOUR_APPID" --secret "YOUR_SECRET" --title "标题" --content "内容" --no-cover
        '''
    )
    parser.add_argument('--appid', type=str, required=True,
                        help='微信公众号 AppID（必填）')
    parser.add_argument('--secret', type=str, required=True,
                        help='微信公众号 AppSecret（必填）')
    parser.add_argument('--article', type=str, metavar='FILE',
                        help='Markdown 文章文件路径')
    parser.add_argument('--title', type=str, metavar='TITLE',
                        help='文章标题（与 --content 配合使用）')
    parser.add_argument('--content', type=str, metavar='CONTENT',
                        help='文章内容（HTML 格式，与 --title 配合使用）')
    parser.add_argument('--author', type=str, default='昌哥',
                        help='作者名（默认：昌哥）')
    parser.add_argument('--image', type=str, metavar='IMAGE_FILE',
                        help='自定义封面图片路径')
    parser.add_argument('--no-cover', action='store_true',
                        help='跳过封面生成，使用默认封面（推荐）')
    
    args = parser.parse_args()
    
    # 创建发布助手
    publisher = WeChatPublisher(args.appid, args.secret)
    publisher.print_config()
    
    # 获取 access_token
    publisher.get_access_token()
    if not publisher.access_token:
        return
    
    # 上传封面图（如果有）
    thumb_media_id = None
    if args.image and os.path.exists(args.image):
        thumb_media_id = publisher.upload_image(args.image)
    elif args.no_cover:
        print("📌 使用默认封面...")
        thumb_media_id = publisher.upload_default_cover()
    
    # 如果有 Markdown 文件
    if args.article:
        publisher.publish_from_markdown(
            markdown_file=args.article,
            title=args.title,
            author=args.author,
            thumb_media_id=thumb_media_id
        )
    # 如果有标题和内容
    elif args.title and args.content:
        # 上传草稿
        media_id = publisher.upload_draft(
            title=args.title,
            content=args.content,
            author=args.author,
            thumb_media_id=thumb_media_id
        )
        if media_id:
            print(f"\n✅ 文章已保存到草稿箱！")
            print(f"   Media ID: {media_id}")
            print(f"\n💡 提示：请前往微信公众号后台 (https://mp.weixin.qq.com/) 查看并发布。\n")
    else:
        print("❌ 请提供文章内容（--article 或 --title + --content）")
        parser.print_help()


if __name__ == '__main__':
    main()
