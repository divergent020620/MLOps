-- Cube Studio 公告功能 - 数据库建表语句
-- 在离线环境 MySQL 中执行此 SQL

CREATE TABLE IF NOT EXISTS announcement (
    created_on DATETIME,
    changed_on DATETIME,
    id INT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL COMMENT '公告标题',
    content TEXT COMMENT '公告内容(Markdown格式)',
    is_active TINYINT(1) DEFAULT 0 COMMENT '是否当前生效',
    created_by_fk INT,
    changed_by_fk INT,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by_fk) REFERENCES ab_user(id),
    FOREIGN KEY (changed_by_fk) REFERENCES ab_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
