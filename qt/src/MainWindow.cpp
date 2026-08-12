#include "MainWindow.h"
#include "TimelineWidget.h"

#include <QActionGroup>
#include <QApplication>
#include <QCheckBox>
#include <QClipboard>
#include <QCloseEvent>
#include <QDateTime>
#include <QDir>
#include <QDragEnterEvent>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontDatabase>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QMenuBar>
#include <QMessageBox>
#include <QMimeData>
#include <QPlainTextEdit>
#include <QProcessEnvironment>
#include <QProgressBar>
#include <QPushButton>
#include <QScrollBar>
#include <QSplitter>
#include <QStatusBar>
#include <QShortcut>
#include <QTableWidget>
#include <QTabWidget>
#include <QTextBlock>
#include <QTextCursor>
#include <QTime>
#include <QToolBar>
#include <QTreeWidget>
#include <QVBoxLayout>

namespace {
constexpr int NodeRole = Qt::UserRole;
constexpr int OffsetRole = Qt::UserRole + 1;
constexpr int SizeRole = Qt::UserRole + 2;
constexpr int FieldRole = Qt::UserRole + 3;

QPushButton *commandButton(const QString &text, const char *name = nullptr)
{
    auto *button = new QPushButton(text);
    button->setMinimumHeight(34);
    if (name)
        button->setObjectName(name);
    return button;
}

QLabel *sectionLabel(const QString &text)
{
    auto *label = new QLabel(text);
    label->setObjectName("sectionLabel");
    return label;
}
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent), m_process(new QProcess(this)),
      m_settings(QDir(qEnvironmentVariable("AVSCOPE_ROOT", "G:/AVScope")).filePath("data/qt-settings.ini"), QSettings::IniFormat)
{
    setWindowTitle(tr("AVScope - 音视频协议分析工作台"));
    resize(1560, 940);
    setMinimumSize(1120, 720);
    setAcceptDrops(true);
    buildUi();
    buildMenus();
    buildShortcuts();
    applyTheme(qEnvironmentVariable("AVSCOPE_THEME").compare("light", Qt::CaseInsensitive) != 0);
    connect(m_process, &QProcess::finished, this, &MainWindow::analysisFinished);
    restoreWorkspaceState();
}

void MainWindow::buildUi()
{
    auto *central = new QWidget;
    central->setObjectName("appRoot");
    auto *rootLayout = new QVBoxLayout(central);
    rootLayout->setContentsMargins(18, 14, 18, 12);
    rootLayout->setSpacing(10);
    rootLayout->addWidget(buildHeader());
    rootLayout->addWidget(buildSummaryStrip());

    m_mainSplitter = new QSplitter(Qt::Horizontal);
    m_mainSplitter->setObjectName("mainSplitter");
    m_mainSplitter->setChildrenCollapsible(false);
    m_mainSplitter->addWidget(buildProtocolPanel());
    m_mainSplitter->addWidget(buildWorkspace());
    m_mainSplitter->addWidget(buildInspector());
    m_mainSplitter->setStretchFactor(0, 2);
    m_mainSplitter->setStretchFactor(1, 6);
    m_mainSplitter->setStretchFactor(2, 2);
    m_mainSplitter->setSizes({390, 800, 330});
    rootLayout->addWidget(m_mainSplitter, 1);

    m_log = new QPlainTextEdit;
    m_log->setObjectName("logPanel");
    m_log->setReadOnly(true);
    m_log->setMaximumHeight(92);
    m_log->appendPlainText(tr("[就绪] Qt 6 工作台已启动，可拖入媒体文件。"));
    rootLayout->addWidget(m_log);
    setCentralWidget(central);

    m_statusText = new QLabel(tr("就绪"));
    statusBar()->addWidget(m_statusText, 1);
    m_progress = new QProgressBar;
    m_progress->setObjectName("analysisProgress");
    m_progress->setRange(0, 0);
    m_progress->setFixedSize(120, 8);
    m_progress->hide();
    statusBar()->addPermanentWidget(m_progress);
    auto *engine = new QLabel(tr("解析引擎 Python Core  |  UI Qt 6.9"));
    engine->setObjectName("statusMeta");
    statusBar()->addPermanentWidget(engine);
}

QWidget *MainWindow::buildHeader()
{
    auto *header = new QFrame;
    header->setObjectName("header");
    auto *layout = new QHBoxLayout(header);
    layout->setContentsMargins(4, 0, 4, 0);
    layout->setSpacing(10);

    auto *mark = new QLabel("AV");
    mark->setObjectName("brandMark");
    mark->setAlignment(Qt::AlignCenter);
    mark->setFixedSize(38, 38);
    auto *brandBox = new QWidget;
    auto *brandLayout = new QVBoxLayout(brandBox);
    brandLayout->setContentsMargins(0, 0, 0, 0);
    brandLayout->setSpacing(0);
    auto *brand = new QLabel("AVScope");
    brand->setObjectName("brandTitle");
    auto *subtitle = new QLabel(tr("音视频协议分析工作台"));
    subtitle->setObjectName("brandSubtitle");
    brandLayout->addWidget(brand);
    brandLayout->addWidget(subtitle);
    layout->addWidget(mark);
    layout->addWidget(brandBox);

    m_fileLabel = new QLabel(tr("尚未打开文件"));
    m_fileLabel->setObjectName("filePill");
    m_fileLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    layout->addWidget(m_fileLabel);
    layout->addStretch();

    m_search = new QLineEdit;
    m_search->setPlaceholderText(tr("搜索节点、字段或值"));
    m_search->setClearButtonEnabled(true);
    m_search->setMinimumWidth(260);
    connect(m_search, &QLineEdit::returnPressed, this, &MainWindow::searchNext);
    connect(m_search, &QLineEdit::textChanged, this, &MainWindow::filterProtocolTree);
    layout->addWidget(m_search);

    auto *open = commandButton(tr("打开文件"), "primaryButton");
    connect(open, &QPushButton::clicked, this, &MainWindow::chooseFile);
    layout->addWidget(open);
    auto *reload = commandButton(tr("重新分析"));
    connect(reload, &QPushButton::clicked, this, &MainWindow::reloadCurrent);
    layout->addWidget(reload);

    m_cancelButton = commandButton(tr("取消"));
    m_cancelButton->setObjectName("dangerButton");
    m_cancelButton->setEnabled(false);
    connect(m_cancelButton, &QPushButton::clicked, this, &MainWindow::cancelAnalysis);
    layout->addWidget(m_cancelButton);

    m_darkButton = commandButton(tr("夜间"));
    m_lightButton = commandButton(tr("浅色"));
    m_darkButton->setCheckable(true);
    m_lightButton->setCheckable(true);
    connect(m_darkButton, &QPushButton::clicked, this, &MainWindow::setDarkTheme);
    connect(m_lightButton, &QPushButton::clicked, this, &MainWindow::setLightTheme);
    layout->addWidget(m_darkButton);
    layout->addWidget(m_lightButton);
    return header;
}

QWidget *MainWindow::buildSummaryStrip()
{
    auto *strip = new QWidget;
    auto *layout = new QHBoxLayout(strip);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(10);
    layout->addWidget(makeMetricCard(tr("识别格式"), &m_formatMetric, "cyan"));
    layout->addWidget(makeMetricCard(tr("文件大小"), &m_sizeMetric, "green"));
    layout->addWidget(makeMetricCard(tr("协议节点 / 字段"), &m_nodeMetric, "violet"));
    layout->addWidget(makeMetricCard(tr("诊断状态"), &m_issueMetric, "amber"));
    return strip;
}

QWidget *MainWindow::makeMetricCard(const QString &label, QLabel **valueLabel, const QString &accent)
{
    auto *card = new QFrame;
    card->setProperty("metricCard", true);
    card->setProperty("accent", accent);
    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(14, 10, 14, 10);
    layout->setSpacing(2);
    auto *caption = new QLabel(label);
    caption->setObjectName("metricLabel");
    *valueLabel = new QLabel("--");
    (*valueLabel)->setObjectName("metricValue");
    layout->addWidget(caption);
    layout->addWidget(*valueLabel);
    return card;
}

QWidget *MainWindow::buildProtocolPanel()
{
    auto *panel = new QFrame;
    panel->setObjectName("panel");
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(8);
    layout->addWidget(sectionLabel(tr("协议树")));
    auto *hint = new QLabel(tr("展开节点可查看每个字段和值"));
    hint->setObjectName("sectionHint");
    layout->addWidget(hint);

    auto *tools = new QWidget;
    auto *toolsLayout = new QHBoxLayout(tools);
    toolsLayout->setContentsMargins(0, 0, 0, 0);
    toolsLayout->setSpacing(6);
    m_issueFilter = new QCheckBox(tr("只看异常"));
    connect(m_issueFilter, &QCheckBox::toggled, this, &MainWindow::filterProtocolTree);
    toolsLayout->addWidget(m_issueFilter);
    auto *expand = commandButton(tr("展开"));
    expand->setMinimumHeight(28);
    connect(expand, &QPushButton::clicked, this, [this] { m_protocolTree->expandAll(); });
    toolsLayout->addWidget(expand);
    auto *collapse = commandButton(tr("折叠"));
    collapse->setMinimumHeight(28);
    connect(collapse, &QPushButton::clicked, this, [this] { m_protocolTree->collapseAll(); });
    toolsLayout->addWidget(collapse);
    toolsLayout->addStretch();
    layout->addWidget(tools);

    m_protocolTree = new QTreeWidget;
    m_protocolTree->setObjectName("protocolTree");
    m_protocolTree->setColumnCount(5);
    m_protocolTree->setHeaderLabels({tr("名称"), tr("类型"), tr("值"), tr("Offset"), tr("Size")});
    m_protocolTree->setAlternatingRowColors(true);
    m_protocolTree->setUniformRowHeights(true);
    m_protocolTree->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_protocolTree->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    m_protocolTree->header()->setStretchLastSection(false);
    m_protocolTree->header()->setSectionResizeMode(0, QHeaderView::Interactive);
    m_protocolTree->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_protocolTree->header()->setSectionResizeMode(2, QHeaderView::Interactive);
    m_protocolTree->header()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    m_protocolTree->header()->setSectionResizeMode(4, QHeaderView::ResizeToContents);
    m_protocolTree->setColumnWidth(0, 220);
    m_protocolTree->setColumnWidth(2, 210);
    connect(m_protocolTree, &QTreeWidget::itemSelectionChanged, this, &MainWindow::onTreeSelectionChanged);
    layout->addWidget(m_protocolTree, 1);
    return panel;
}

QWidget *MainWindow::buildWorkspace()
{
    auto *panel = new QFrame;
    panel->setObjectName("panel");
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(0, 0, 0, 0);
    m_tabs = new QTabWidget;
    m_tabs->setDocumentMode(true);
    m_tabs->setMovable(true);

    m_hexView = new QPlainTextEdit;
    m_hexView->setReadOnly(true);
    m_hexView->setLineWrapMode(QPlainTextEdit::NoWrap);
    m_hexView->setFont(QFontDatabase::systemFont(QFontDatabase::FixedFont));
    m_hexView->setPlaceholderText(tr("选择协议节点或字段后显示对应 Hex 区域"));
    m_tabs->addTab(m_hexView, tr("Hex"));

    m_fieldsTable = new QTableWidget;
    m_fieldsTable->setColumnCount(7);
    m_fieldsTable->setHorizontalHeaderLabels({tr("字段"), tr("值"), tr("Hex"), tr("Offset"), tr("Bit / Size"), tr("状态"), tr("说明")});
    m_fieldsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_fieldsTable->setAlternatingRowColors(true);
    m_fieldsTable->verticalHeader()->hide();
    m_fieldsTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
    connect(m_fieldsTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::onFieldSelectionChanged);
    m_tabs->addTab(m_fieldsTable, tr("字段"));

    m_framesTable = new QTableWidget;
    m_framesTable->setColumnCount(8);
    m_framesTable->setHorizontalHeaderLabels({"#", "Offset", "Size", "PTS", "DTS", "Duration", tr("类型"), "Key"});
    m_framesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_framesTable->setAlternatingRowColors(true);
    m_framesTable->verticalHeader()->hide();
    m_framesTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
    connect(m_framesTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::onFrameSelectionChanged);
    m_tabs->addTab(m_framesTable, tr("帧列表"));

    m_timeline = new TimelineWidget;
    connect(m_timeline, &TimelineWidget::frameSelected, this, [this](int row) {
        if (row < 0 || row >= m_framesTable->rowCount()) return;
        m_framesTable->selectRow(row);
        m_framesTable->scrollToItem(m_framesTable->item(row, 0));
        m_tabs->setCurrentWidget(m_framesTable);
    });
    m_tabs->addTab(m_timeline, tr("时间线"));

    m_preview = new QPlainTextEdit;
    m_preview->setReadOnly(true);
    m_preview->setLineWrapMode(QPlainTextEdit::WidgetWidth);
    m_tabs->addTab(m_preview, tr("媒体摘要"));
    layout->addWidget(m_tabs);
    return panel;
}

QWidget *MainWindow::buildInspector()
{
    auto *panel = new QFrame;
    panel->setObjectName("panel");
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(8);
    layout->addWidget(sectionLabel(tr("当前选择")));
    auto *selectionHint = new QLabel(tr("节点、字段位置与语义详情"));
    selectionHint->setObjectName("sectionHint");
    layout->addWidget(selectionHint);
    m_selectionDetails = new QPlainTextEdit;
    m_selectionDetails->setObjectName("selectionDetails");
    m_selectionDetails->setReadOnly(true);
    m_selectionDetails->setMaximumHeight(260);
    m_selectionDetails->setPlaceholderText(tr("选择协议节点或字段后显示详情"));
    layout->addWidget(m_selectionDetails);
    layout->addWidget(sectionLabel(tr("全局诊断")));
    auto *hint = new QLabel(tr("warning / error 与媒体探测摘要"));
    hint->setObjectName("sectionHint");
    layout->addWidget(hint);
    m_diagnosticsTable = new QTableWidget;
    m_diagnosticsTable->setColumnCount(4);
    m_diagnosticsTable->setHorizontalHeaderLabels({tr("级别"), tr("来源"), tr("Offset"), tr("问题")});
    m_diagnosticsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_diagnosticsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_diagnosticsTable->setAlternatingRowColors(true);
    m_diagnosticsTable->verticalHeader()->hide();
    m_diagnosticsTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_diagnosticsTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_diagnosticsTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    m_diagnosticsTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    connect(m_diagnosticsTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::onDiagnosticSelectionChanged);
    layout->addWidget(m_diagnosticsTable, 1);
    return panel;
}

void MainWindow::buildMenus()
{
    auto *fileMenu = menuBar()->addMenu(tr("文件"));
    auto *open = fileMenu->addAction(tr("打开文件..."), QKeySequence::Open);
    connect(open, &QAction::triggered, this, &MainWindow::chooseFile);
    auto *reload = fileMenu->addAction(tr("重新分析"), QKeySequence::Refresh);
    connect(reload, &QAction::triggered, this, &MainWindow::reloadCurrent);
    auto *cancel = fileMenu->addAction(tr("取消当前分析"), QKeySequence(Qt::Key_Escape));
    connect(cancel, &QAction::triggered, this, &MainWindow::cancelAnalysis);
    m_recentMenu = fileMenu->addMenu(tr("最近文件"));
    rebuildRecentMenu();
    fileMenu->addSeparator();
    auto *html = fileMenu->addAction(tr("导出 HTML 报告..."));
    connect(html, &QAction::triggered, this, &MainWindow::exportHtml);
    auto *json = fileMenu->addAction(tr("导出 JSON 报告..."));
    connect(json, &QAction::triggered, this, &MainWindow::exportJson);
    fileMenu->addSeparator();
    fileMenu->addAction(tr("退出"), qApp, &QApplication::quit);

    auto *viewMenu = menuBar()->addMenu(tr("视图"));
    auto *themes = new QActionGroup(this);
    auto *dark = viewMenu->addAction(tr("夜间主题"));
    auto *light = viewMenu->addAction(tr("浅色主题"));
    dark->setCheckable(true);
    light->setCheckable(true);
    dark->setChecked(true);
    themes->addAction(dark);
    themes->addAction(light);
    connect(dark, &QAction::triggered, this, &MainWindow::setDarkTheme);
    connect(light, &QAction::triggered, this, &MainWindow::setLightTheme);
    viewMenu->addSeparator();
    viewMenu->addAction(tr("展开协议树"), QKeySequence("Ctrl+Shift+E"), m_protocolTree, &QTreeWidget::expandAll);
    viewMenu->addAction(tr("折叠协议树"), QKeySequence("Ctrl+Shift+C"), m_protocolTree, &QTreeWidget::collapseAll);

    auto *editMenu = menuBar()->addMenu(tr("编辑"));
    editMenu->addAction(tr("复制当前 Offset"), QKeySequence("Ctrl+Shift+O"), this, &MainWindow::copyCurrentOffset);
    editMenu->addAction(tr("复制当前值"), QKeySequence::Copy, this, &MainWindow::copyCurrentValue);

    auto *helpMenu = menuBar()->addMenu(tr("帮助"));
    helpMenu->addAction(tr("关于 AVScope"), this, [this] {
        QMessageBox::about(this, tr("关于 AVScope"),
                           tr("AVScope %1\nQt 6 现代桌面工作台\nPython 协议解析核心").arg(QApplication::applicationVersion()));
    });
}

void MainWindow::buildShortcuts()
{
    auto *focusSearch = new QShortcut(QKeySequence::Find, this);
    connect(focusSearch, &QShortcut::activated, m_search, [this] { m_search->setFocus(); m_search->selectAll(); });
    for (int index = 0; index < 5; ++index) {
        auto *shortcut = new QShortcut(QKeySequence(QString("Ctrl+%1").arg(index + 1)), this);
        connect(shortcut, &QShortcut::activated, this, [this, index] { m_tabs->setCurrentIndex(index); });
    }
}

void MainWindow::addRecentFile(const QString &path)
{
    QStringList recent = m_settings.value("recentFiles").toStringList();
    recent.removeAll(path);
    recent.prepend(path);
    while (recent.size() > 12)
        recent.removeLast();
    m_settings.setValue("recentFiles", recent);
    rebuildRecentMenu();
}

void MainWindow::rebuildRecentMenu()
{
    if (!m_recentMenu)
        return;
    m_recentMenu->clear();
    const QStringList recent = m_settings.value("recentFiles").toStringList();
    bool added = false;
    for (const QString &path : recent) {
        if (!QFileInfo::exists(path))
            continue;
        added = true;
        auto *action = m_recentMenu->addAction(QFileInfo(path).fileName());
        action->setToolTip(path);
        connect(action, &QAction::triggered, this, [this, path] { openPath(path); });
    }
    if (!added) {
        auto *empty = m_recentMenu->addAction(tr("暂无最近文件"));
        empty->setEnabled(false);
    } else {
        m_recentMenu->addSeparator();
        m_recentMenu->addAction(tr("清空最近文件"), this, [this] {
            m_settings.remove("recentFiles");
            rebuildRecentMenu();
        });
    }
}

void MainWindow::restoreWorkspaceState()
{
    const QByteArray geometry = m_settings.value("windowGeometry").toByteArray();
    if (!geometry.isEmpty())
        restoreGeometry(geometry);
    const QByteArray splitterState = m_settings.value("splitterState").toByteArray();
    if (!splitterState.isEmpty())
        m_mainSplitter->restoreState(splitterState);
    m_tabs->setCurrentIndex(qBound(0, m_settings.value("currentTab", 0).toInt(), m_tabs->count() - 1));
    if (qEnvironmentVariableIsEmpty("AVSCOPE_THEME"))
        applyTheme(m_settings.value("theme", "dark").toString() != "light");
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    if (m_process->state() != QProcess::NotRunning) {
        m_cancelRequested = true;
        m_process->kill();
        m_process->waitForFinished(1000);
    }
    m_settings.setValue("windowGeometry", saveGeometry());
    m_settings.setValue("splitterState", m_mainSplitter->saveState());
    m_settings.setValue("currentTab", m_tabs->currentIndex());
    m_settings.sync();
    QMainWindow::closeEvent(event);
}

void MainWindow::chooseFile()
{
    const auto path = QFileDialog::getOpenFileName(this, tr("打开音视频或协议文件"), "G:/AVScope/samples");
    if (!path.isEmpty())
        openPath(path);
}

void MainWindow::reloadCurrent()
{
    if (!m_currentPath.isEmpty())
        openPath(m_currentPath);
}

void MainWindow::cancelAnalysis()
{
    if (m_process->state() == QProcess::NotRunning)
        return;
    m_cancelRequested = true;
    m_statusText->setText(tr("正在取消分析..."));
    m_process->terminate();
    if (!m_process->waitForFinished(1200))
        m_process->kill();
}

void MainWindow::openPath(const QString &path)
{
    const QFileInfo info(path);
    if (!info.exists() || !info.isFile()) {
        QMessageBox::warning(this, tr("无法打开"), tr("文件不存在：\n%1").arg(path));
        return;
    }
    if (m_process->state() != QProcess::NotRunning) {
        QMessageBox::information(this, tr("正在分析"), tr("请等待当前分析完成。"));
        return;
    }

    m_currentPath = info.absoluteFilePath();
    m_cancelRequested = false;
    QDir().mkpath(projectRoot() + "/tmp/qt-runtime");
    QFile::remove(analysisOutputPath());
    m_fileLabel->setText(info.fileName());
    m_statusText->setText(tr("正在分析 %1...").arg(info.fileName()));
    m_log->appendPlainText(tr("[%1] 开始分析 %2").arg(QTime::currentTime().toString("HH:mm:ss"), m_currentPath));

    auto environment = QProcessEnvironment::systemEnvironment();
    environment.insert("PYTHONPATH", projectRoot());
    environment.insert("TEMP", projectRoot() + "/tmp");
    environment.insert("TMP", projectRoot() + "/tmp");
    m_process->setProcessEnvironment(environment);
    m_process->setWorkingDirectory(projectRoot());
    setAnalysisBusy(true);
    m_process->start(engineExecutable(), engineArguments({"analyze", m_currentPath, "--json", analysisOutputPath()}));
}

void MainWindow::analysisFinished(int exitCode, QProcess::ExitStatus status)
{
    setAnalysisBusy(false);
    if (m_cancelRequested) {
        m_cancelRequested = false;
        m_statusText->setText(tr("分析已取消"));
        m_log->appendPlainText(tr("[%1] 用户取消分析").arg(QTime::currentTime().toString("HH:mm:ss")));
        return;
    }
    if (status != QProcess::NormalExit || exitCode != 0) {
        const auto error = QString::fromUtf8(m_process->readAllStandardError());
        m_statusText->setText(tr("分析失败"));
        m_log->appendPlainText(tr("[错误] %1").arg(error));
        QMessageBox::critical(this, tr("分析失败"), error.isEmpty() ? tr("解析进程异常退出。") : error);
        return;
    }
    QFile file(analysisOutputPath());
    if (!file.open(QIODevice::ReadOnly)) {
        QMessageBox::critical(this, tr("读取失败"), tr("无法读取解析结果：%1").arg(analysisOutputPath()));
        return;
    }
    QJsonParseError parseError;
    const auto document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (document.isNull()) {
        QMessageBox::critical(this, tr("结果无效"), parseError.errorString());
        return;
    }
    loadDocument(document);
    const auto info = QFileInfo(m_currentPath);
    addRecentFile(m_currentPath);
    m_statusText->setText(tr("%1  |  分析完成").arg(info.fileName()));
    m_log->appendPlainText(tr("[%1] 分析完成").arg(QTime::currentTime().toString("HH:mm:ss")));
}

void MainWindow::setAnalysisBusy(bool busy)
{
    m_cancelButton->setEnabled(busy);
    m_progress->setVisible(busy);
    m_search->setEnabled(!busy);
    if (busy)
        QApplication::setOverrideCursor(Qt::BusyCursor);
    else if (QApplication::overrideCursor())
        QApplication::restoreOverrideCursor();
}

void MainWindow::loadDocument(const QJsonDocument &document)
{
    m_document = document;
    const auto object = document.object();
    const auto media = object.value("media").toObject();
    const auto root = object.value("root").toObject();
    const auto frames = object.value("frames").toArray();
    const auto diagnostics = object.value("diagnostics").toArray();

    m_protocolTree->clear();
    populateProtocolTree(root);
    filterProtocolTree();
    m_protocolTree->expandToDepth(1);
    if (auto *rootItem = m_protocolTree->topLevelItem(0)) {
        QTreeWidgetItem *selection = rootItem;
        if (rootItem->childCount() > 0) {
            selection = rootItem->child(0);
            if (selection->childCount() > 0)
                selection = selection->child(0);
        }
        m_protocolTree->setCurrentItem(selection);
        m_protocolTree->scrollToItem(selection);
    }
    populateFrames(frames);
    populateDiagnostics(diagnostics, media);
    m_timeline->setData(frames, media.value("summary").toObject().value("timeline_summary").toObject());

    m_formatMetric->setText(media.value("format_name").toString("--"));
    m_sizeMetric->setText(formatSize(jsonInteger(media.value("size"))));
    m_nodeMetric->setText(tr("%1 / %2").arg(countNodes(root)).arg(countFields(root)));
    m_issueMetric->setText(diagnostics.isEmpty() ? tr("通过") : tr("%1 项").arg(diagnostics.size()));
    m_fileLabel->setToolTip(media.value("path").toString());

    const auto summary = media.value("summary").toObject();
    QStringList lines;
    lines << tr("文件：%1").arg(media.value("path").toString())
          << tr("格式：%1").arg(media.value("format_name").toString())
          << tr("大小：%1").arg(formatSize(jsonInteger(media.value("size"))))
          << ""
          << tr("结构化媒体摘要")
          << QString::fromUtf8(QJsonDocument(summary).toJson(QJsonDocument::Indented));
    m_preview->setPlainText(lines.join('\n'));
    showHex(0, 1);
    const auto requestedTab = qEnvironmentVariable("AVSCOPE_START_TAB");
    if (!requestedTab.isEmpty()) {
        bool ok = false;
        const int index = requestedTab.toInt(&ok);
        if (ok && index >= 0 && index < m_tabs->count())
            m_tabs->setCurrentIndex(index);
    }
}

void MainWindow::populateProtocolTree(const QJsonObject &node, QTreeWidgetItem *parent)
{
    auto *item = parent ? new QTreeWidgetItem(parent) : new QTreeWidgetItem(m_protocolTree);
    const qint64 offset = jsonInteger(node.value("offset"));
    const qint64 size = jsonInteger(node.value("size"));
    item->setText(0, node.value("name").toString());
    item->setText(1, node.value("node_type").toString());
    item->setText(3, QString("0x%1").arg(offset, 0, 16).toUpper());
    item->setText(4, QString::number(size));
    item->setData(0, NodeRole, node);
    item->setData(0, OffsetRole, offset);
    item->setData(0, SizeRole, size);
    item->setToolTip(0, node.value("description").toString());
    const QString severity = node.value("severity").toString();
    if (severity == "warning")
        item->setForeground(0, QColor("#D79B32"));
    else if (severity == "error")
        item->setForeground(0, QColor("#EA5B62"));

    for (const auto &fieldValue : node.value("fields").toArray()) {
        const auto field = fieldValue.toObject();
        auto *fieldItem = new QTreeWidgetItem(item);
        const qint64 fieldOffset = jsonInteger(field.value("offset"));
        qint64 fieldSize = jsonInteger(field.value("size"));
        if (fieldSize <= 0)
            fieldSize = qMax<qint64>(1, (jsonInteger(field.value("bit_length")) + 7) / 8);
        fieldItem->setText(0, field.value("name").toString());
        fieldItem->setText(1, tr("字段"));
        fieldItem->setText(2, displayValue(field.value("value")));
        fieldItem->setText(3, QString("0x%1").arg(fieldOffset, 0, 16).toUpper());
        fieldItem->setText(4, QString::number(fieldSize));
        fieldItem->setData(0, NodeRole, node);
        fieldItem->setData(0, FieldRole, field);
        fieldItem->setData(0, OffsetRole, fieldOffset);
        fieldItem->setData(0, SizeRole, fieldSize);
        fieldItem->setToolTip(0, field.value("description").toString());
        const auto color = fieldColor(field.value("value"), field.value("hex_value").toString(), field.value("severity").toString());
        for (int column = 0; column < m_protocolTree->columnCount(); ++column)
            fieldItem->setForeground(column, color);
    }
    for (const auto &child : node.value("children").toArray())
        populateProtocolTree(child.toObject(), item);
}

void MainWindow::onTreeSelectionChanged()
{
    const auto selected = m_protocolTree->selectedItems();
    if (selected.isEmpty())
        return;
    auto *item = selected.constFirst();
    const auto node = item->data(0, NodeRole).toJsonObject();
    const auto field = item->data(0, FieldRole).toJsonObject();
    populateFields(node);
    showSelectionDetails(node, field);
    const qint64 offset = item->data(0, OffsetRole).toLongLong();
    const qint64 size = item->data(0, SizeRole).toLongLong();
    showHex(offset, size);
    m_statusText->setText(tr("Offset 0x%1  |  %2 bytes").arg(offset, 0, 16).arg(size));
}

void MainWindow::populateFields(const QJsonObject &node)
{
    const auto fields = node.value("fields").toArray();
    m_fieldsTable->setRowCount(fields.size());
    for (int row = 0; row < fields.size(); ++row) {
        const auto field = fields.at(row).toObject();
        const qint64 offset = jsonInteger(field.value("offset"));
        qint64 size = jsonInteger(field.value("size"));
        const qint64 bitOffset = jsonInteger(field.value("bit_offset"));
        const qint64 bitLength = jsonInteger(field.value("bit_length"));
        if (size <= 0)
            size = qMax<qint64>(1, (bitLength + 7) / 8);
        const QString bits = field.value("bit_offset").isNull() && field.value("bit_length").isNull()
            ? QString::number(size) : QString("%1/%2").arg(bitOffset).arg(bitLength);
        const QStringList values = {
            field.value("name").toString(), displayValue(field.value("value")), field.value("hex_value").toString(),
            QString("0x%1").arg(offset, 0, 16).toUpper(), bits, field.value("severity").toString(), field.value("description").toString()
        };
        const auto color = fieldColor(field.value("value"), field.value("hex_value").toString(), field.value("severity").toString());
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setForeground(color);
            cell->setData(OffsetRole, offset);
            cell->setData(SizeRole, size);
            m_fieldsTable->setItem(row, column, cell);
        }
    }
    m_fieldsTable->resizeColumnsToContents();
    m_fieldsTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
}

void MainWindow::onFieldSelectionChanged()
{
    const auto selected = m_fieldsTable->selectedItems();
    if (selected.isEmpty())
        return;
    const auto *item = selected.constFirst();
    showHex(item->data(OffsetRole).toLongLong(), item->data(SizeRole).toLongLong());
    const int row = item->row();
    const auto nodeItems = m_protocolTree->selectedItems();
    if (!nodeItems.isEmpty()) {
        const auto fields = nodeItems.constFirst()->data(0, NodeRole).toJsonObject().value("fields").toArray();
        if (row >= 0 && row < fields.size())
            showSelectionDetails(nodeItems.constFirst()->data(0, NodeRole).toJsonObject(), fields.at(row).toObject());
    }
}

void MainWindow::populateFrames(const QJsonArray &frames)
{
    const int rows = qMin(frames.size(), 5000);
    m_framesTable->setRowCount(rows);
    for (int row = 0; row < rows; ++row) {
        const auto frame = frames.at(row).toObject();
        const QStringList values = {
            QString::number(jsonInteger(frame.value("index"))),
            QString("0x%1").arg(jsonInteger(frame.value("offset")), 0, 16).toUpper(),
            QString::number(jsonInteger(frame.value("size"))), displayValue(frame.value("pts")), displayValue(frame.value("dts")),
            displayValue(frame.value("duration")), frame.value("frame_type").toString(), frame.value("keyframe").toBool() ? tr("是") : QString()
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, jsonInteger(frame.value("offset")));
            cell->setData(SizeRole, jsonInteger(frame.value("size")));
            m_framesTable->setItem(row, column, cell);
        }
    }
    m_framesTable->resizeColumnsToContents();
    m_framesTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
}

void MainWindow::onFrameSelectionChanged()
{
    const auto selected = m_framesTable->selectedItems();
    if (selected.isEmpty())
        return;
    const auto *item = selected.constFirst();
    showHex(item->data(OffsetRole).toLongLong(), item->data(SizeRole).toLongLong());
    m_statusText->setText(tr("帧 #%1  |  Offset 0x%2  |  %3 bytes")
                              .arg(m_framesTable->item(item->row(), 0)->text())
                              .arg(item->data(OffsetRole).toLongLong(), 0, 16)
                              .arg(item->data(SizeRole).toLongLong()));
}

void MainWindow::showSelectionDetails(const QJsonObject &node, const QJsonObject &field)
{
    QStringList lines;
    lines << tr("节点")
          << tr("名称  %1").arg(node.value("name").toString())
          << tr("类型  %1").arg(node.value("node_type").toString())
          << tr("范围  0x%1 + %2 bytes").arg(jsonInteger(node.value("offset")), 0, 16).arg(jsonInteger(node.value("size")))
          << tr("状态  %1").arg(node.value("severity").toString());
    if (!node.value("description").toString().isEmpty())
        lines << tr("说明  %1").arg(node.value("description").toString());
    if (!field.isEmpty()) {
        lines << "" << tr("字段")
              << tr("名称  %1").arg(field.value("name").toString())
              << tr("值    %1").arg(displayValue(field.value("value")))
              << tr("Hex   %1").arg(field.value("hex_value").toString())
              << tr("Offset  0x%1").arg(jsonInteger(field.value("offset")), 0, 16)
              << tr("字节长度  %1").arg(jsonInteger(field.value("size")));
        if (!field.value("bit_offset").isNull() || !field.value("bit_length").isNull())
            lines << tr("Bit  %1 / %2").arg(jsonInteger(field.value("bit_offset"))).arg(jsonInteger(field.value("bit_length")));
        lines << tr("状态  %1").arg(field.value("severity").toString());
        if (!field.value("description").toString().isEmpty())
            lines << tr("说明  %1").arg(field.value("description").toString());
    }
    m_selectionDetails->setPlainText(lines.join('\n'));
}

void MainWindow::populateDiagnostics(const QJsonArray &diagnostics, const QJsonObject &media)
{
    m_diagnosticsTable->setRowCount(qMax(1, diagnostics.size()));
    if (diagnostics.isEmpty()) {
        const QStringList values = {tr("通过"), media.value("format_name").toString(), QString(), tr("未发现 warning / error")};
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_diagnosticsTable->setItem(0, column, cell);
        }
        return;
    }
    for (int row = 0; row < diagnostics.size(); ++row) {
        const auto issue = diagnostics.at(row).toObject();
        const QString severity = issue.value("severity").toString();
        const bool hasOffset = !issue.value("offset").isNull();
        const qint64 offset = hasOffset ? jsonInteger(issue.value("offset")) : -1;
        const QStringList values = {
            severity.toUpper(), issue.value("source").toString(),
            hasOffset ? QString("0x%1").arg(offset, 0, 16).toUpper() : QString(), issue.value("message").toString()
        };
        const QColor color = severity == "error" ? QColor(m_dark ? "#FF7B81" : "#B42318")
                                                   : QColor(m_dark ? "#F5C567" : "#8A5A00");
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setForeground(color);
            cell->setToolTip(issue.value("message").toString());
            cell->setData(OffsetRole, offset);
            m_diagnosticsTable->setItem(row, column, cell);
        }
    }
}

void MainWindow::onDiagnosticSelectionChanged()
{
    const auto selected = m_diagnosticsTable->selectedItems();
    if (selected.isEmpty()) return;
    const qint64 offset = selected.constFirst()->data(OffsetRole).toLongLong();
    if (offset < 0) return;
    showHex(offset, 1);
    m_tabs->setCurrentWidget(m_hexView);
    m_statusText->setText(tr("诊断定位到 Offset 0x%1").arg(offset, 0, 16).toUpper());
}

void MainWindow::showHex(qint64 offset, qint64 size)
{
    QFile file(m_currentPath);
    if (!file.open(QIODevice::ReadOnly))
        return;
    const qint64 start = qMax<qint64>(0, (offset / 16) * 16 - 64);
    file.seek(start);
    const QByteArray data = file.read(16 * 48);
    QStringList lines;
    for (int lineOffset = 0; lineOffset < data.size(); lineOffset += 16) {
        const QByteArray chunk = data.mid(lineOffset, 16);
        QStringList hex;
        QString ascii;
        for (const auto byte : chunk) {
            hex << QString("%1").arg(static_cast<unsigned char>(byte), 2, 16, QLatin1Char('0')).toUpper();
            const auto value = static_cast<unsigned char>(byte);
            ascii += value >= 32 && value <= 126 ? QChar(value) : QChar('.');
        }
        const QString address = QString("%1").arg(start + lineOffset, 8, 16, QLatin1Char('0')).toUpper();
        lines << QString("%1  %2  |%3|").arg(address, hex.join(' ').leftJustified(47, ' '), ascii);
    }
    m_hexView->setPlainText(lines.join('\n'));
    const int line = qBound(0, static_cast<int>((offset - start) / 16), qMax(0, lines.size() - 1));
    QTextCursor cursor(m_hexView->document()->findBlockByLineNumber(line));
    cursor.select(QTextCursor::LineUnderCursor);
    m_hexView->setTextCursor(cursor);
    m_hexView->centerCursor();
    m_hexView->setToolTip(tr("选中范围：0x%1，%2 bytes").arg(offset, 0, 16).arg(size));
}

void MainWindow::searchNext()
{
    const QString query = m_search->text().trimmed();
    if (query.isEmpty())
        return;
    QTreeWidgetItemIterator it(m_protocolTree);
    bool afterCurrent = m_protocolTree->selectedItems().isEmpty();
    while (*it) {
        auto *item = *it;
        if (!afterCurrent) {
            afterCurrent = m_protocolTree->selectedItems().contains(item);
            ++it;
            continue;
        }
        QString content;
        for (int column = 0; column < item->columnCount(); ++column)
            content += item->text(column) + ' ';
        if (content.contains(query, Qt::CaseInsensitive)) {
            m_protocolTree->setCurrentItem(item);
            m_protocolTree->scrollToItem(item);
            return;
        }
        ++it;
    }
    m_statusText->setText(tr("未找到：%1").arg(query));
}

void MainWindow::filterProtocolTree()
{
    if (!m_protocolTree)
        return;
    const QString query = m_search ? m_search->text().trimmed() : QString();
    const bool issuesOnly = m_issueFilter && m_issueFilter->isChecked();
    for (int index = 0; index < m_protocolTree->topLevelItemCount(); ++index)
        filterTreeItem(m_protocolTree->topLevelItem(index), query, issuesOnly);
    if (!query.isEmpty() || issuesOnly)
        m_protocolTree->expandAll();
}

bool MainWindow::filterTreeItem(QTreeWidgetItem *item, const QString &query, bool issuesOnly)
{
    bool childVisible = false;
    for (int index = 0; index < item->childCount(); ++index)
        childVisible = filterTreeItem(item->child(index), query, issuesOnly) || childVisible;

    QString content;
    for (int column = 0; column < item->columnCount(); ++column)
        content += item->text(column) + ' ';
    const bool queryMatch = query.isEmpty() || content.contains(query, Qt::CaseInsensitive);
    const auto node = item->data(0, NodeRole).toJsonObject();
    const auto field = item->data(0, FieldRole).toJsonObject();
    const QString severity = field.isEmpty() ? node.value("severity").toString() : field.value("severity").toString();
    const bool issueMatch = !issuesOnly || severity == "warning" || severity == "error" || childVisible;
    const bool visible = childVisible || (queryMatch && issueMatch);
    item->setHidden(!visible);
    return visible;
}

void MainWindow::copyCurrentOffset()
{
    const auto selected = m_protocolTree->selectedItems();
    if (selected.isEmpty())
        return;
    const qint64 offset = selected.constFirst()->data(0, OffsetRole).toLongLong();
    QApplication::clipboard()->setText(QString("0x%1").arg(offset, 0, 16).toUpper());
    m_statusText->setText(tr("已复制 Offset 0x%1").arg(offset, 0, 16).toUpper());
}

void MainWindow::copyCurrentValue()
{
    const auto selected = m_protocolTree->selectedItems();
    if (selected.isEmpty())
        return;
    auto *item = selected.constFirst();
    const QString value = item->data(0, FieldRole).toJsonObject().isEmpty() ? item->text(0) : item->text(2);
    QApplication::clipboard()->setText(value);
    m_statusText->setText(tr("已复制当前值"));
}

void MainWindow::exportHtml()
{
    if (m_currentPath.isEmpty())
        return;
    const auto path = QFileDialog::getSaveFileName(this, tr("导出 HTML 报告"), "G:/AVScope/tmp/AVScope-report.html", "HTML (*.html)");
    if (!path.isEmpty())
        runExport("html", path);
}

void MainWindow::exportJson()
{
    if (m_currentPath.isEmpty())
        return;
    const auto path = QFileDialog::getSaveFileName(this, tr("导出 JSON 报告"), "G:/AVScope/tmp/AVScope-report.json", "JSON (*.json)");
    if (!path.isEmpty())
        runExport("json", path);
}

void MainWindow::runExport(const QString &format, const QString &outputPath)
{
    QProcess process;
    process.setWorkingDirectory(projectRoot());
    auto environment = QProcessEnvironment::systemEnvironment();
    environment.insert("PYTHONPATH", projectRoot());
    environment.insert("TEMP", projectRoot() + "/tmp");
    environment.insert("TMP", projectRoot() + "/tmp");
    process.setProcessEnvironment(environment);
    process.start(engineExecutable(), engineArguments({"analyze", m_currentPath, "--" + format, outputPath}));
    if (!process.waitForFinished(120000) || process.exitCode() != 0) {
        QMessageBox::critical(this, tr("导出失败"), QString::fromUtf8(process.readAllStandardError()));
        return;
    }
    m_log->appendPlainText(tr("[导出] %1").arg(outputPath));
    m_statusText->setText(tr("报告已导出：%1").arg(outputPath));
}

void MainWindow::setDarkTheme() { applyTheme(true); }
void MainWindow::setLightTheme() { applyTheme(false); }

void MainWindow::applyTheme(bool dark)
{
    m_dark = dark;
    m_settings.setValue("theme", dark ? "dark" : "light");
    m_darkButton->setChecked(dark);
    m_lightButton->setChecked(!dark);
    const QString bg = dark ? "#0C1117" : "#F3F6F9";
    const QString panel = dark ? "#121A22" : "#FFFFFF";
    const QString panelAlt = dark ? "#17212B" : "#EDF2F6";
    const QString text = dark ? "#E7EDF3" : "#172331";
    const QString muted = dark ? "#94A3B2" : "#607080";
    const QString border = dark ? "#273442" : "#D8E1E8";
    const QString select = dark ? "#23678D" : "#B9DCF3";
    const QString selectText = dark ? "#FFFFFF" : "#102A43";
    const QString hover = dark ? "#1E303E" : "#E2EDF5";

    qApp->setStyleSheet(QString(R"(
        QMainWindow, #appRoot { background: %1; color: %4; }
        QMenuBar { background: %1; color: %4; padding: 4px 8px; }
        QMenuBar::item:selected, QMenu::item:selected { background: %7; color: %8; }
        QMenu { background: %2; color: %4; border: 1px solid %6; padding: 5px; }
        QStatusBar { background: %3; color: %5; border-top: 1px solid %6; }
        #header { background: transparent; }
        #brandMark { background: #2F91C7; color: white; border-radius: 7px; font-weight: 700; font-size: 12px; }
        #brandTitle { color: %4; font-size: 20px; font-weight: 700; }
        #brandSubtitle, #sectionHint, #metricLabel, #statusMeta { color: %5; font-size: 11px; }
        #filePill { color: %5; background: %3; border: 1px solid %6; border-radius: 5px; padding: 6px 10px; }
        QPushButton { color: %4; background: %2; border: 1px solid %6; border-radius: 5px; padding: 6px 12px; }
        QPushButton:hover { background: %9; border-color: #2F91C7; }
        QPushButton:checked { background: %7; color: %8; border-color: #2F91C7; }
        #primaryButton { background: #247DAA; color: white; border-color: #247DAA; font-weight: 600; }
        #primaryButton:hover { background: #2F91C7; }
        QLineEdit { color: %4; background: %2; border: 1px solid %6; border-radius: 5px; padding: 7px 10px; selection-background-color: %7; selection-color: %8; }
        QFrame#panel, QFrame[metricCard="true"] { background: %2; border: 1px solid %6; border-radius: 7px; }
        QFrame[metricCard="true"] { border-left: 3px solid #2F91C7; }
        #metricValue { color: %4; font-size: 16px; font-weight: 700; }
        #sectionLabel { color: %4; font-size: 13px; font-weight: 700; }
        QTreeWidget, QTableWidget, QPlainTextEdit { background: %2; alternate-background-color: %3; color: %4; border: 0; selection-background-color: %7; selection-color: %8; gridline-color: %6; }
        QTreeView::item, QTableView::item { min-height: 25px; padding: 3px 5px; }
        QTreeView::item:selected, QTableView::item:selected { background: %7; color: %8; }
        QHeaderView::section { background: %3; color: %5; border: 0; border-right: 1px solid %6; border-bottom: 1px solid %6; padding: 7px; font-weight: 600; }
        QTabWidget::pane { border: 0; background: %2; }
        QTabBar::tab { background: %3; color: %5; padding: 9px 16px; border-right: 1px solid %6; }
        QTabBar::tab:selected { background: %2; color: %4; border-top: 2px solid #2F91C7; }
        QSplitter::handle { background: %1; width: 7px; }
        QScrollBar:vertical, QScrollBar:horizontal { background: %3; border: 0; margin: 0; }
        QScrollBar::handle { background: %6; border-radius: 3px; min-width: 28px; min-height: 28px; }
        #logPanel { background: %3; color: %5; border: 1px solid %6; border-radius: 6px; }
    )").arg(bg, panel, panelAlt, text, muted, border, select, selectText, hover));
    m_timeline->setDarkTheme(dark);
    if (!m_document.isNull())
        loadDocument(m_document);
}

void MainWindow::dragEnterEvent(QDragEnterEvent *event)
{
    if (event->mimeData()->hasUrls() && !event->mimeData()->urls().isEmpty())
        event->acceptProposedAction();
}

void MainWindow::dropEvent(QDropEvent *event)
{
    const auto urls = event->mimeData()->urls();
    if (!urls.isEmpty() && urls.constFirst().isLocalFile()) {
        openPath(urls.constFirst().toLocalFile());
        event->acceptProposedAction();
    }
}

QString MainWindow::projectRoot() const
{
    const auto env = qEnvironmentVariable("AVSCOPE_ROOT");
    if (!env.isEmpty())
        return QDir::cleanPath(env);
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 6; ++i) {
        if (QFileInfo::exists(dir.filePath("avscope/cli.py")))
            return dir.absolutePath();
        dir.cdUp();
    }
    return "G:/AVScope";
}

QString MainWindow::pythonExecutable() const
{
    const auto env = qEnvironmentVariable("AVSCOPE_PYTHON");
    return env.isEmpty() ? QString("E:/DevelopmentEnvironment/python/python.exe") : env;
}

QString MainWindow::engineExecutable() const
{
    const auto override = qEnvironmentVariable("AVSCOPE_ENGINE");
    if (!override.isEmpty() && QFileInfo::exists(override))
        return override;
    const QDir appDir(QCoreApplication::applicationDirPath());
    const QString bundled = appDir.filePath("engine/AVScopeEngine.exe");
    if (QFileInfo::exists(bundled))
        return bundled;
    return pythonExecutable();
}

QStringList MainWindow::engineArguments(const QStringList &arguments) const
{
    if (engineExecutable().endsWith(".exe", Qt::CaseInsensitive)
        && QFileInfo(engineExecutable()).fileName().compare("AVScopeEngine.exe", Qt::CaseInsensitive) == 0)
        return arguments;
    QStringList result = {"-m", "avscope"};
    result.append(arguments);
    return result;
}

QString MainWindow::analysisOutputPath() const
{
    return projectRoot() + "/tmp/qt-runtime/current-analysis.json";
}

QColor MainWindow::fieldColor(const QJsonValue &value, const QString &hex, const QString &severity) const
{
    if (severity == "error") return QColor(m_dark ? "#FF7B81" : "#B42318");
    if (severity == "warning") return QColor(m_dark ? "#F5C567" : "#8A5A00");
    if (value.isBool()) return QColor(m_dark ? "#FFC978" : "#855100");
    if (value.isDouble()) return QColor(m_dark ? "#8FD694" : "#176B3A");
    if (!hex.isEmpty()) return QColor(m_dark ? "#C5A3FF" : "#6641A5");
    return QColor(m_dark ? "#8BC6FF" : "#1D5D92");
}

QString MainWindow::displayValue(const QJsonValue &value)
{
    if (value.isNull() || value.isUndefined()) return QString();
    if (value.isBool()) return value.toBool() ? "true" : "false";
    if (value.isDouble()) return QString::number(value.toDouble(), 'g', 14);
    if (value.isString()) return value.toString();
    if (value.isArray()) return QString::fromUtf8(QJsonDocument(value.toArray()).toJson(QJsonDocument::Compact));
    if (value.isObject()) return QString::fromUtf8(QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact));
    return value.toVariant().toString();
}

qint64 MainWindow::jsonInteger(const QJsonValue &value)
{
    return value.isDouble() ? static_cast<qint64>(value.toDouble()) : value.toVariant().toLongLong();
}

QString MainWindow::formatSize(qint64 bytes)
{
    if (bytes < 1024) return tr("%1 B").arg(bytes);
    if (bytes < 1024 * 1024) return tr("%1 KB").arg(bytes / 1024.0, 0, 'f', 1);
    if (bytes < 1024LL * 1024 * 1024) return tr("%1 MB").arg(bytes / 1024.0 / 1024.0, 0, 'f', 1);
    return tr("%1 GB").arg(bytes / 1024.0 / 1024.0 / 1024.0, 0, 'f', 2);
}

int MainWindow::countNodes(const QJsonObject &node)
{
    int count = 1;
    for (const auto &child : node.value("children").toArray()) count += countNodes(child.toObject());
    return count;
}

int MainWindow::countFields(const QJsonObject &node)
{
    int count = node.value("fields").toArray().size();
    for (const auto &child : node.value("children").toArray()) count += countFields(child.toObject());
    return count;
}
