-- 数据卷首次初始化时由 PG 官方镜像自动执行（仅空卷时运行一次）
-- 开发库 docmind 由 compose 的 POSTGRES_DB 创建，这里只补测试库
CREATE DATABASE docmind_test;
