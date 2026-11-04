#!/usr/bin/env python3
"""
导出用户订阅到OPML文件
"""

import requests
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree, tostring
from xml.dom import minidom


API_BASE = "http://localhost:8000"
USERNAME = "test-user"
PASSWORD = "test123"


def login():
    """登录获取token"""
    response = requests.post(
        f"{API_BASE}/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token"), data.get("user", {}).get("id")
    else:
        print(f"登录失败: {response.status_code}")
        return None, None


def get_all_feeds(token: str, user_id: str):
    """获取所有订阅"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{API_BASE}/user/{user_id}/feeds",
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        # API返回格式: {"status": "success", "feeds": [...]}
        return data.get("feeds", [])
    else:
        print(f"获取订阅失败: {response.status_code} - {response.text}")
        return []


def prettify_xml(elem):
    """美化XML输出"""
    rough_string = tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="    ", encoding="UTF-8")


def export_to_opml(feeds, output_file):
    """导出feeds到OPML格式"""

    # 创建OPML根元素
    opml = Element('opml', version='2.0')

    # 创建head
    head = SubElement(opml, 'head')
    title = SubElement(head, 'title')
    title.text = 'Jasmine Feeds - test-user'
    dateCreated = SubElement(head, 'dateCreated')
    dateCreated.text = datetime.now().isoformat()

    # 创建body
    body = SubElement(opml, 'body')

    # 按分类组织feeds
    categories = {}

    for feed in feeds:
        # 尝试从feed名称推断分类
        feed_name = feed.get('feed_name', 'Unknown')
        feed_url = feed.get('feed_url', '')

        # 简单分类逻辑
        category = 'Articles'  # 默认分类

        if any(keyword in feed_url.lower() for keyword in ['bilibili', 'youtube']):
            category = 'Videos'
        elif any(keyword in feed_url.lower() for keyword in ['pixiv', 'javdb', 'javbus', 'javtiful', '7mmtv', '141jav', 'missav']):
            category = 'Pictures'
        elif any(keyword in feed_url.lower() for keyword in ['xiaoyuzhou', 'podcast']):
            category = 'Audios'
        elif any(keyword in feed_url.lower() for keyword in ['xueqiu', 'jinse', 'wallstreetcn']):
            category = 'Notifications'
        elif 'wechat' in feed_url.lower():
            category = 'WeChat'
        elif any(keyword in feed_name for keyword in ['bilibili', 'B站']):
            category = 'SocialMedia'

        if category not in categories:
            categories[category] = []

        categories[category].append(feed)

    # 为每个分类创建outline
    for category, category_feeds in sorted(categories.items()):
        category_outline = SubElement(body, 'outline', text=category)

        for feed in sorted(category_feeds, key=lambda x: x.get('feed_name', '')):
            feed_name = feed.get('feed_name', 'Unknown')
            feed_url = feed.get('feed_url', '')

            # 创建feed outline
            SubElement(category_outline, 'outline',
                      text=feed_name,
                      title=feed_name,
                      type='rss',
                      xmlUrl=feed_url,
                      htmlUrl=feed_url)

    # 美化并写入文件
    pretty_xml = prettify_xml(opml)

    with open(output_file, 'wb') as f:
        f.write(pretty_xml)

    print(f'✓ OPML 文件已导出到: {output_file}')
    print(f'  总计 {len(feeds)} 个订阅')
    print(f'  分类数: {len(categories)}')
    for category, feeds_list in sorted(categories.items()):
        print(f'    - {category}: {len(feeds_list)} 个')


def main():
    """主函数"""
    print('='*80)
    print('Jasmine 订阅导出工具')
    print('='*80)

    # 登录
    print('\n正在登录...')
    token, user_id = login()
    if not token:
        print('登录失败，退出')
        return
    print(f'✓ 登录成功: {user_id}\n')

    # 获取所有feeds
    print('正在获取订阅列表...')
    feeds = get_all_feeds(token, user_id)

    if not feeds:
        print('⚠ 没有找到订阅')
        return

    print(f'✓ 找到 {len(feeds)} 个订阅\n')

    # 显示所有feeds
    print('订阅列表:')
    print('-'*80)
    for i, feed in enumerate(feeds, 1):
        feed_name = feed.get('feed_name', 'Unknown')
        feed_url = feed.get('feed_url', '')
        print(f'{i:2d}. {feed_name}')
        print(f'    {feed_url}')
    print('-'*80)

    # 导出到OPML
    output_file = f'data/feeds/feed_source/jasmine_feeds_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.opml'
    print(f'\n正在导出到 {output_file}...')

    export_to_opml(feeds, output_file)

    print('\n✓ 导出完成!')
    print('='*80)


if __name__ == '__main__':
    main()
