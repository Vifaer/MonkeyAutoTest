#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理冗余代码脚本
用于删除或标记不再需要的文件和代码

使用前请先备份项目！
"""

import os
import sys
import shutil
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 需要删除的文件列表（完全冗余）
FILES_TO_DELETE = [
    "utils/pytest_integration.py",  # 完全冗余，功能已被tests/和conftest.py替代
]

# 需要评估的文件列表（可能冗余）
FILES_TO_EVALUATE = [
    "test_stability_basic.py",  # 非pytest格式，需要评估是否仍在使用
    "test_modular_stability.py",  # 非pytest格式，功能已被tests/替代
    "test_baseline_functionality.py",  # 非pytest格式，需要评估
    "test_auto_get_apk.py",  # 非pytest格式，需要评估
    "run_stability_test.py",  # 功能与main.py重复，需要评估
]

# 需要备份的文件（删除前备份）
BACKUP_DIR = project_root / "backup_before_cleanup"


def create_backup():
    """创建备份目录"""
    if BACKUP_DIR.exists():
        print(f"⚠️  备份目录已存在: {BACKUP_DIR}")
        response = input("是否删除旧备份并创建新备份? (y/n): ")
        if response.lower() != 'y':
            return False
        shutil.rmtree(BACKUP_DIR)
    
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ 创建备份目录: {BACKUP_DIR}")
    return True


def backup_file(file_path):
    """备份单个文件"""
    src = project_root / file_path
    if not src.exists():
        print(f"⚠️  文件不存在: {file_path}")
        return False
    
    dst = BACKUP_DIR / file_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"✅ 已备份: {file_path} -> {dst}")
    return True


def delete_file(file_path):
    """删除文件"""
    src = project_root / file_path
    if not src.exists():
        print(f"⚠️  文件不存在: {file_path}")
        return False
    
    try:
        src.unlink()
        print(f"✅ 已删除: {file_path}")
        return True
    except Exception as e:
        print(f"❌ 删除失败: {file_path}, 错误: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("Monkey自动化测试项目 - 冗余代码清理脚本")
    print("=" * 60)
    print()
    
    # 确认操作
    print("⚠️  警告: 此脚本将删除以下文件:")
    print("\n完全冗余的文件（将删除）:")
    for f in FILES_TO_DELETE:
        print(f"  - {f}")
    
    print("\n需要评估的文件（仅列出，不删除）:")
    for f in FILES_TO_EVALUATE:
        print(f"  - {f}")
    
    print("\n" + "=" * 60)
    response = input("是否继续? (yes/no): ")
    if response.lower() != 'yes':
        print("操作已取消")
        return
    
    # 创建备份
    print("\n创建备份...")
    if not create_backup():
        print("备份创建失败，操作已取消")
        return
    
    # 备份要删除的文件
    print("\n备份要删除的文件...")
    for file_path in FILES_TO_DELETE:
        backup_file(file_path)
    
    # 删除文件
    print("\n删除冗余文件...")
    deleted_count = 0
    for file_path in FILES_TO_DELETE:
        if delete_file(file_path):
            deleted_count += 1
    
    print("\n" + "=" * 60)
    print(f"清理完成!")
    print(f"  - 已删除文件: {deleted_count}/{len(FILES_TO_DELETE)}")
    print(f"  - 备份位置: {BACKUP_DIR}")
    print("\n需要评估的文件:")
    for f in FILES_TO_EVALUATE:
        print(f"  - {f}")
    print("\n请手动评估这些文件，决定是否迁移到pytest格式或删除")


if __name__ == "__main__":
    main()
