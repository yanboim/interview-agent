# 前端工具链审计门禁

## 基线

经评审的开发基线为Node 20.19或更高版本上的Vite 8、
`@vitejs/plugin-vue` 6、vue-tsc 3和Vitest 4。根声明和 `package-lock.json` 中解析的
包都必须满足基线。

## 门禁

`frontend/scripts/check-toolchain.mjs` 不访问Registry，直接读取包元数据；必需包缺失、
解析版本低于已评审主版本或与Lockfile不一致时失败。该检查属于
`make frontend-check`。

CI还以 `moderate` 严重度运行完整npm审计，包括开发依赖。该规则有意比之前的
`high` 阈值严格，因为原6项发现属于构建期依赖警告。

`@vue/test-utils` 继续精确固定在2.2.7。无关的2.4.11更新会引入带6个high审计发现的
`js-beautify` 依赖链，因此有意排除在本次Vite/vue-tsc升级外。

## 范围

前端构建阶段结束后，构建期包不进入Python运行镜像。但它们仍影响源码转换和开发机，
所以版本、Integrity、测试和审计状态仍属于发布输入。
