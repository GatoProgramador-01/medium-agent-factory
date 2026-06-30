// @ts-check

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: "Medium Agent Factory",
  tagline:
    "16-node LangGraph pipeline that writes Medium posts with AI quality gates",
  favicon: "img/favicon.ico",

  url: "https://GatoProgramador-01.github.io",
  baseUrl: "/medium-agent-factory/",

  organizationName: "GatoProgramador-01",
  projectName: "medium-agent-factory",
  trailingSlash: false,

  onBrokenLinks: "warn",

  i18n: {
    defaultLocale: "en",
    locales: ["en"],
  },

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: "warn",
    },
  },

  themes: ["@docusaurus/theme-mermaid"],

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: require.resolve("./sidebars.js"),
          editUrl:
            "https://github.com/GatoProgramador-01/medium-agent-factory/tree/master/website/",
        },
        blog: false,
        theme: {
          customCss: require.resolve("./src/css/custom.css"),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: "Medium Agent Factory",
        items: [
          {
            type: "docSidebar",
            sidebarId: "tutorialSidebar",
            position: "left",
            label: "Docs",
          },
          {
            href: "https://github.com/GatoProgramador-01/medium-agent-factory",
            label: "GitHub",
            position: "right",
          },
        ],
      },
      footer: {
        style: "dark",
        links: [
          {
            title: "Docs",
            items: [
              {
                label: "Introduction",
                to: "/docs/intro",
              },
              {
                label: "Pipeline Overview",
                to: "/docs/pipeline-overview",
              },
              {
                label: "Quality Gates",
                to: "/docs/quality-gates",
              },
              {
                label: "Prompt Engineering",
                to: "/docs/prompt-engineering",
              },
            ],
          },
          {
            title: "Project",
            items: [
              {
                label: "GitHub",
                href: "https://github.com/GatoProgramador-01/medium-agent-factory",
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} GatoProgramador-01. Built with Docusaurus. MIT License.`,
      },
      mermaid: {
        theme: { light: "neutral", dark: "forest" },
      },
    }),
};

module.exports = config;
