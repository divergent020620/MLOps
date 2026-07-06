/**
 * 右下角公告浮动按钮组件
 *
 * 功能：
 * - 固定在页面右下角，蓝色圆形按钮 + 铃铛图标
 * - 有未读公告时显示红点（通过对比 localStorage 中的 dismissed_id 和当前公告 id 判断）
 * - 点击铃铛 → 触发 onClick 回调，由 App 层重新打开公告弹窗
 * - 无生效公告时（announcement === null）完全隐藏，不渲染任何 DOM
 */

import React, { useState, useEffect } from 'react';
import { Badge, Button, Tooltip } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import type { AnnouncementData } from './AnnouncementModal';

interface AnnouncementBadgeProps {
  /** 当前生效的公告数据。为 null 时整个组件不渲染 */
  announcement: AnnouncementData | null;
  /** 点击按钮时的回调，通常用于重新打开公告弹窗 */
  onClick: () => void;
}

// localStorage key，与 AnnouncementModal 保持一致
const STORAGE_KEY_ID = 'announcement_last_dismissed_id';

const AnnouncementBadge: React.FC<AnnouncementBadgeProps> = ({
  announcement,
  onClick,
}) => {
  // 是否显示红点（未读标记）
  const [showDot, setShowDot] = useState(false);

  /**
   * 每当公告数据更新时，重新判断是否需要显示红点：
   * - 从未关闭过公告（localStorage 中无记录） → 显示红点
   * - 关闭的公告 id ≠ 当前生效公告 id（有新公告） → 显示红点
   * - 已关闭过当前公告                       → 不显示红点
   */
  useEffect(() => {
    if (!announcement) {
      setShowDot(false);
      return;
    }

    const dismissedId = localStorage.getItem(STORAGE_KEY_ID);
    // 红点条件：从未关闭过 或 关闭的是旧公告
    setShowDot(!dismissedId || dismissedId !== String(announcement.id));
  }, [announcement]);

  /** 点击按钮时立即清除红点（因为用户主动查看了公告） */
  const handleClick = () => {
    setShowDot(false);
    onClick();
  };

  // 无生效公告时完全不渲染
  if (!announcement) {
    return null;
  }

  return (
    <Tooltip
      title={announcement.title || '系统公告'}
      placement="left"  // 提示文字出现在按钮左侧，避免被屏幕右边界截断
    >
      <div
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 1000,  // 确保在大多数元素之上
        }}
      >
        {/*
          Badge 的 dot 属性为 true 时在按钮右上角显示红点，
          offset 微调红点位置使其对齐按钮边缘
        */}
        <Badge dot={showDot} offset={[-2, 6]}>
          <Button
            type="primary"
            shape="circle"
            size="large"
            icon={<BellOutlined style={{ fontSize: 20 }} />}
            onClick={handleClick}
            style={{
              width: 48,
              height: 48,
              boxShadow: '0 2px 8px rgba(0,0,0,0.15)',  // 轻微阴影突出层次
            }}
          />
        </Badge>
      </div>
    </Tooltip>
  );
};

export default AnnouncementBadge;
