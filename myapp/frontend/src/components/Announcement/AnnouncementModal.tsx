/**
 * 公告弹窗组件
 *
 * 在首页加载时自动获取最新生效公告并弹出。
 *
 * 弹出规则（通过 localStorage 判断）：
 * - 用户当天未关闭过此公告 → 弹出
 * - 管理员发布了新公告（id 与上次关闭的不同）→ 弹出（当天也会弹）
 * - 用户已关闭过公告，且当天无新公告 → 不弹出
 *
 * localStorage key 设计：
 * - announcement_last_dismissed_date : "2026-06-12" 格式，上次关闭时的日期
 * - announcement_last_dismissed_id   : 上次关闭的公告 ID，用于判断是否有新公告
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Modal } from 'antd';
// marked —— 项目已安装的 Markdown → HTML 转换库，无需新增依赖
import { marked } from 'marked';
import axios from 'axios';
import './Announcement.less';

// ================================================================
// 类型定义
// ================================================================

/** 后端 /latest/ 接口返回的公告数据结构 */
export interface AnnouncementData {
  id: number;
  title: string;
  content: string;       // Markdown 格式文本
  is_active: boolean;
  created_on: string | null;
}

interface AnnouncementModalProps {
  /**
   * 弹窗关闭后的回调：
   * - 传入公告对象 → 通知父组件存在生效公告（用于显示 Badge）
   * - 传入 null    → 通知父组件无生效公告（隐藏 Badge）
   */
  onDismiss?: (announcement: AnnouncementData | null) => void;
  /**
   * 强制弹出模式：
   * - true → 跳过 localStorage 检查，有公告就直接弹（Badge 点击时使用）
   * - false/undefined → 正常逻辑（页面加载时使用）
   */
  forceOpen?: boolean;
}

// ================================================================
// localStorage 键名常量
// ================================================================

const STORAGE_KEY_DATE = 'announcement_last_dismissed_date';
const STORAGE_KEY_ID = 'announcement_last_dismissed_id';

// ================================================================
// 组件
// ================================================================

const AnnouncementModal: React.FC<AnnouncementModalProps> = ({ onDismiss, forceOpen }) => {
  // 弹窗是否可见
  const [visible, setVisible] = useState(false);
  // 当前生效公告完整数据（为 null 表示无生效公告或尚未加载）
  const [announcement, setAnnouncement] = useState<AnnouncementData | null>(null);
  // Markdown → HTML 渲染后的内容
  const [htmlContent, setHtmlContent] = useState('');

  /**
   * 获取今天的日期字符串，格式 "YYYY-MM-DD"
   * 用于和 localStorage 中记录的关闭日期对比
   */
  const getTodayStr = (): string => {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  /**
   * 请求后端 /latest/ 接口获取当前生效公告，
   * 然后根据 localStorage 中的关闭记录决定是否弹出
   */
  const fetchLatestAnnouncement = useCallback(async () => {
    try {
      // 请求最新生效公告（后端查询 is_active=True 的最新一条）
      const response = await axios.get('/announcement_modelview/api/latest/');

      // 后端返回 { data: {...}, status: 0, message: 'ok' } 或 { data: null, status: 0 }
      const data = response.data?.data ?? response.data?.result;
      // 使用局部变量接收公告数据

      if (data && data.id) {
        // 有生效公告
        setAnnouncement(data);

        // 将 Markdown 转为 HTML（marked.parse 返回 Promise<string>）
        const html = await marked.parse(data.content || '');
        setHtmlContent(html);

        // forceOpen：Badge 点击触发的强制弹出，跳过 localStorage 检查
        if (forceOpen) {
          setVisible(true);
        } else {
          // 读取 localStorage 中的关闭记录
          const dismissedDate = localStorage.getItem(STORAGE_KEY_DATE);
          const dismissedId = localStorage.getItem(STORAGE_KEY_ID);
          const today = getTodayStr();

          // 弹窗条件：
          // 条件1：今天还没关闭过（日期不同）
          // 条件2：关闭的不是当前公告（有新公告发布了）
          const shouldPopup =
            dismissedDate !== today || dismissedId !== String(data.id);

          if (shouldPopup) {
            setVisible(true);
          } else {
            // 不需要弹窗，但通知父组件有公告存在（用于在右下角显示 Badge）
            onDismiss?.(data);
          }
        }
      } else {
        // 后端返回 null → 当前无生效公告，通知父组件隐藏 Badge
        setAnnouncement(null);
        onDismiss?.(null);
      }
    } catch (err) {
      // 请求失败时静默处理：不弹窗、不报错（避免影响正常使用）
      console.error('获取公告失败:', err);
    }
  }, [onDismiss, forceOpen]);

  // 组件挂载时自动获取公告
  useEffect(() => {
    fetchLatestAnnouncement();
  }, [fetchLatestAnnouncement]);

  /**
   * 关闭弹窗
   * 将当前日期和公告 ID 写入 localStorage，通知父组件更新 Badge
   */
  const handleClose = () => {
    setVisible(false);

    // 记录关闭的日期和公告 ID
    localStorage.setItem(STORAGE_KEY_DATE, getTodayStr());
    if (announcement) {
      localStorage.setItem(STORAGE_KEY_ID, String(announcement.id));
    }

    // 通知父组件（父组件用于更新 Badge 红点状态和显示/隐藏）
    onDismiss?.(announcement);
  };

  // 无公告时不渲染任何 DOM
  if (!announcement) {
    return null;
  }

  return (
    <Modal
      // 标题栏：公告图标 + 公告标题
      title={'📢 ' + (announcement.title || '系统公告')}
      open={visible}
      onCancel={handleClose}
      // 底部只显示一个「知道了」按钮
      footer={[
        <button
          key="ok"
          onClick={handleClose}
          style={{
            padding: '4px 24px',
            background: '#1890ff',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          知道了
        </button>,
      ]}
      width={650}                     // 弹窗宽度，适配一般公告长度
      destroyOnClose                  // 关闭时销毁 DOM，避免残留
      maskClosable={false}            // 不允许点遮罩关闭，必须点击「知道了」
      centered                        // 屏幕居中显示
      className="announcement-modal"  // 自定义样式类名，见 Announcement.less
    >
      {/*
        使用 dangerouslySetInnerHTML 渲染 Markdown 生成的 HTML。
        内容由管理员编辑后存入数据库，前端仅渲染展示，不存在 XSS 风险。
      */}
      <div
        className="announcement-content"
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
    </Modal>
  );
};

export default AnnouncementModal;
