#include "MainWindow.h"
#include "HexCompareWidget.h"
#include "HexView.h"
#include "MediaPreviewWidget.h"
#include "TimelineWidget.h"

#include <QActionGroup>
#include <QApplication>
#include <QCheckBox>
#include <QClipboard>
#include <QCloseEvent>
#include <QComboBox>
#include <QDateTime>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
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
#include <QStandardPaths>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QInputDialog>
#include <QIcon>
#include <QMenuBar>
#include <QMessageBox>
#include <QMimeData>
#include <QPlainTextEdit>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>
#include <QProcessEnvironment>
#include <QProgressBar>
#include <QPushButton>
#include <QScrollBar>
#include <QSet>
#include <QSignalBlocker>
#include <QSplitter>
#include <QStatusBar>
#include <QShortcut>
#include <QSpinBox>
#include <QTableWidget>
#include <QTabBar>
#include <QTabWidget>
#include <QTextBlock>
#include <QTextCursor>
#include <QTextEdit>
#include <QTime>
#include <QTimer>
#include <QToolBar>
#include <QTreeWidget>
#include <QTreeWidgetItemIterator>
#include <QVBoxLayout>

#include <limits>

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

QTableWidget *readOnlyTable()
{
    auto *table = new QTableWidget;
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    return table;
}

QLabel *sectionLabel(const QString &text)
{
    auto *label = new QLabel(text);
    label->setObjectName("sectionLabel");
    return label;
}

QIcon protocolTreeIcon(bool field, bool container, bool root, const QString &severity, bool dark)
{
    QPixmap pixmap(18, 18);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);

    const QColor outline = dark ? QColor("#7F95A7") : QColor("#607789");
    const QColor nodeFill = dark ? QColor("#244C63") : QColor("#DCEEF8");
    const QColor fieldFill = dark ? QColor("#24333F") : QColor("#F5F8FA");

    if (root) {
        painter.setPen(Qt::NoPen);
        painter.setBrush(dark ? QColor("#3A93BD") : QColor("#2F83AD"));
        painter.drawRoundedRect(QRectF(1.5, 3.0, 15.0, 12.5), 3.0, 3.0);
        QPolygonF play;
        play << QPointF(7.1, 6.2) << QPointF(12.2, 9.2) << QPointF(7.1, 12.2);
        painter.setBrush(Qt::white);
        painter.drawPolygon(play);
    } else if (container) {
        painter.setPen(QPen(outline, 1.1));
        painter.setBrush(nodeFill);
        painter.drawRoundedRect(QRectF(2.0, 5.2, 14.0, 10.5), 2.0, 2.0);
        painter.setPen(Qt::NoPen);
        painter.setBrush(dark ? QColor("#57A8CB") : QColor("#4D9DC2"));
        painter.drawRoundedRect(QRectF(3.0, 2.5, 7.0, 4.5), 1.3, 1.3);
        painter.setPen(QPen(dark ? QColor("#9ED2E7") : QColor("#317A9C"), 1.0));
        painter.drawLine(QPointF(5.0, 9.0), QPointF(13.0, 9.0));
        painter.drawLine(QPointF(5.0, 12.0), QPointF(11.0, 12.0));
    } else {
        painter.setPen(QPen(outline, 1.1));
        painter.setBrush(field ? fieldFill : nodeFill);
        QPainterPath page;
        page.moveTo(3.5, 1.8);
        page.lineTo(11.2, 1.8);
        page.lineTo(15.0, 5.7);
        page.lineTo(15.0, 16.0);
        page.lineTo(3.5, 16.0);
        page.closeSubpath();
        painter.drawPath(page);
        painter.drawLine(QPointF(11.2, 2.0), QPointF(11.2, 5.8));
        painter.drawLine(QPointF(11.2, 5.8), QPointF(14.8, 5.8));
        painter.setPen(QPen(field ? (dark ? QColor("#8FA7B9") : QColor("#7890A0"))
                                  : (dark ? QColor("#69B4D5") : QColor("#3287AD")), 1.0));
        painter.drawLine(QPointF(6.0, 9.0), QPointF(12.5, 9.0));
        painter.drawLine(QPointF(6.0, 12.0), QPointF(11.0, 12.0));
    }

    if (severity == "warning" || severity == "error") {
        const QColor badge = severity == "error"
            ? (dark ? QColor("#FF7780") : QColor("#D64550"))
            : (dark ? QColor("#F2BE5C") : QColor("#C88413"));
        painter.setPen(QPen(dark ? QColor("#121A22") : Qt::white, 1.0));
        painter.setBrush(badge);
        painter.drawEllipse(QRectF(11.0, 11.0, 6.0, 6.0));
    }

    return QIcon(pixmap);
}
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent), m_process(new QProcess(this)),
      m_settings(QDir(qEnvironmentVariable("AVSCOPE_ROOT", QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation))).filePath("data/qt-settings.ini"), QSettings::IniFormat)
{
    setWindowTitle(tr("AVScope - 音视频协议分析工作台"));
    setWindowIcon(QIcon(":/icons/avscope.png"));
    setMinimumSize(1120, 720);
    setAcceptDrops(true);
    buildUi();
    buildMenus();
    buildShortcuts();
    const QString requestedTheme = qEnvironmentVariable("AVSCOPE_THEME");
    const QString savedTheme = m_settings.value("theme", "dark").toString();
    applyTheme((requestedTheme.isEmpty() ? savedTheme : requestedTheme).compare("light", Qt::CaseInsensitive) != 0, false);
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
    m_inspector = buildInspector();
    m_mainSplitter->addWidget(m_inspector);
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

    m_openButton = commandButton(tr("打开文件"), "primaryButton");
    connect(m_openButton, &QPushButton::clicked, this, &MainWindow::chooseFile);
    layout->addWidget(m_openButton);
    m_reloadButton = commandButton(tr("重新分析"));
    connect(m_reloadButton, &QPushButton::clicked, this, &MainWindow::reloadCurrent);
    layout->addWidget(m_reloadButton);

    m_cancelButton = commandButton(tr("取消"));
    m_cancelButton->setObjectName("dangerButton");
    m_cancelButton->setEnabled(false);
    connect(m_cancelButton, &QPushButton::clicked, this, &MainWindow::cancelAnalysis);
    layout->addWidget(m_cancelButton);

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
    m_protocolTree->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_protocolTree->setObjectName("protocolTree");
    m_protocolTree->setColumnCount(5);
    m_protocolTree->setHeaderLabels({tr("名称"), tr("类型"), tr("值"), tr("Offset"), tr("Size")});
    m_protocolTree->setAlternatingRowColors(true);
    m_protocolTree->setUniformRowHeights(true);
    m_protocolTree->setAnimated(true);
    m_protocolTree->setIndentation(19);
    m_protocolTree->setIconSize(QSize(18, 18));
    m_protocolTree->setAllColumnsShowFocus(true);
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
    m_tabs->tabBar()->setUsesScrollButtons(false);
    m_tabs->tabBar()->setElideMode(Qt::ElideRight);

    m_hexPanel = new QWidget;
    auto *hexLayout = new QVBoxLayout(m_hexPanel);
    hexLayout->setContentsMargins(8, 8, 8, 8);
    hexLayout->setSpacing(6);
    auto *hexTools = new QHBoxLayout;
    m_hexPreviousPage = commandButton(tr("上一页"));
    m_hexPreviousPage->setToolTip(tr("查看前一页 Hex 数据"));
    m_hexNextPage = commandButton(tr("下一页"));
    m_hexNextPage->setToolTip(tr("查看后一页 Hex 数据"));
    m_hexOffsetEdit = new QLineEdit;
    m_hexOffsetEdit->setPlaceholderText(tr("Offset，例如 0x1000"));
    m_hexOffsetEdit->setClearButtonEnabled(true);
    m_hexOffsetEdit->setMaximumWidth(180);
    m_hexPageSizeCombo = new QComboBox;
    m_hexPageSizeCombo->addItem(tr("1 KiB / 页"), 1024);
    m_hexPageSizeCombo->addItem(tr("4 KiB / 页"), 4 * 1024);
    m_hexPageSizeCombo->addItem(tr("16 KiB / 页"), 16 * 1024);
    m_hexPageSizeCombo->addItem(tr("64 KiB / 页"), 64 * 1024);
    m_hexPageSizeCombo->setCurrentIndex(1);
    m_hexRangeLabel = new QLabel(tr("尚未打开文件"));
    m_hexRangeLabel->setObjectName("sectionHint");
    m_hexRangeLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    hexTools->addWidget(m_hexPreviousPage);
    hexTools->addWidget(m_hexNextPage);
    hexTools->addWidget(m_hexOffsetEdit);
    hexTools->addWidget(m_hexPageSizeCombo);
    hexTools->addWidget(m_hexRangeLabel, 1);
    hexLayout->addLayout(hexTools);

    m_hexView = new HexView;
    m_hexView->setReadOnly(true);
    m_hexView->setLineWrapMode(QPlainTextEdit::NoWrap);
    m_hexView->setFont(QFontDatabase::systemFont(QFontDatabase::FixedFont));
    m_hexView->setPlaceholderText(tr("选择协议节点或字段后显示对应 Hex 区域"));
    m_hexView->setToolTip(tr("鼠标拖选默认限制在 Offset、Hex 或 ASCII 列内；按住 Ctrl 可跨列选择"));
    hexLayout->addWidget(m_hexView, 1);
    connect(m_hexPreviousPage, &QPushButton::clicked, this, [this] {
        renderHexPage(qMax<qint64>(0, m_hexPageStart - m_hexPageSize));
    });
    connect(m_hexNextPage, &QPushButton::clicked, this, [this] {
        renderHexPage(m_hexPageStart + m_hexPageSize);
    });
    connect(m_hexOffsetEdit, &QLineEdit::returnPressed, this, [this] {
        QString text = m_hexOffsetEdit->text().trimmed();
        int base = 10;
        if (text.startsWith("0x", Qt::CaseInsensitive)) {
            text.remove(0, 2);
            base = 16;
        }
        bool ok = false;
        const qint64 offset = text.toLongLong(&ok, base);
        if (ok) showHex(offset, 1);
    });
    connect(m_hexPageSizeCombo, &QComboBox::currentIndexChanged, this, [this] {
        m_hexPageSize = m_hexPageSizeCombo->currentData().toLongLong();
        showHex(m_hexOffset, 1);
    });
    m_tabs->addTab(m_hexPanel, tr("Hex"));

    m_fieldsTable = readOnlyTable();
    m_fieldsTable->setColumnCount(7);
    m_fieldsTable->setHorizontalHeaderLabels({tr("字段"), tr("值"), tr("Hex"), tr("Offset"), tr("Bit / Size"), tr("状态"), tr("说明")});
    m_fieldsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_fieldsTable->setAlternatingRowColors(true);
    m_fieldsTable->verticalHeader()->hide();
    m_fieldsTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
    m_fieldsTable->setToolTip(tr("选中字段后按 Ctrl+C 复制字段值"));
    connect(m_fieldsTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::onFieldSelectionChanged);
    m_tabs->addTab(m_fieldsTable, tr("字段"));

    m_framesPanel = new QWidget;
    auto *framesLayout = new QVBoxLayout(m_framesPanel);
    framesLayout->setContentsMargins(8, 8, 8, 8);
    framesLayout->setSpacing(6);
    auto *framesTools = new QHBoxLayout;
    auto *previousFrameButton = commandButton(tr("上一帧"));
    auto *nextFrameButton = commandButton(tr("下一帧"));
    auto *previousKeyframeButton = commandButton(tr("上一关键帧"));
    auto *nextKeyframeButton = commandButton(tr("下一关键帧"));
    m_framesSummary = new QLabel(tr("当前文件没有帧数据"));
    m_framesSummary->setObjectName("sectionHint");
    framesTools->addWidget(previousFrameButton);
    framesTools->addWidget(nextFrameButton);
    framesTools->addWidget(previousKeyframeButton);
    framesTools->addWidget(nextKeyframeButton);
    framesTools->addWidget(m_framesSummary, 1);
    framesLayout->addLayout(framesTools);
    m_framesTable = readOnlyTable();
    m_framesTable->setColumnCount(8);
    m_framesTable->setHorizontalHeaderLabels({"#", "Offset", "Size", "PTS", "DTS", "Duration", tr("类型"), "Key"});
    m_framesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_framesTable->setAlternatingRowColors(true);
    m_framesTable->verticalHeader()->hide();
    m_framesTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
    connect(m_framesTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::onFrameSelectionChanged);
    connect(m_framesTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        if (!item) return;
        showHex(item->data(OffsetRole).toLongLong(), item->data(SizeRole).toLongLong());
        m_tabs->setCurrentWidget(m_hexPanel);
    });
    connect(previousFrameButton, &QPushButton::clicked, this, [this] {
        if (m_framesTable->rowCount() > 0) m_framesTable->selectRow(qMax(0, m_framesTable->currentRow() - 1));
    });
    connect(nextFrameButton, &QPushButton::clicked, this, [this] {
        if (m_framesTable->rowCount() > 0) m_framesTable->selectRow(qMin(m_framesTable->rowCount() - 1, m_framesTable->currentRow() + 1));
    });
    const auto jumpKeyframe = [this](int direction) {
        if (m_framesTable->rowCount() <= 0) return;
        int row = m_framesTable->currentRow();
        if (row < 0) row = direction > 0 ? -1 : m_framesTable->rowCount();
        for (row += direction; row >= 0 && row < m_framesTable->rowCount(); row += direction) {
            if (m_framesTable->item(row, 7) && !m_framesTable->item(row, 7)->text().isEmpty()) {
                m_framesTable->selectRow(row);
                m_framesTable->scrollToItem(m_framesTable->item(row, 0));
                return;
            }
        }
    };
    connect(previousKeyframeButton, &QPushButton::clicked, this, [jumpKeyframe] { jumpKeyframe(-1); });
    connect(nextKeyframeButton, &QPushButton::clicked, this, [jumpKeyframe] { jumpKeyframe(1); });
    connect(m_framesTable, &QTableWidget::itemSelectionChanged, this, [this] {
        const int row = m_framesTable->currentRow();
        if (row >= 0)
            m_framesSummary->setText(tr("第 %1 / %2 项").arg(row + 1).arg(m_framesTable->rowCount()));
    });
    framesLayout->addWidget(m_framesTable, 1);
    m_tabs->addTab(m_framesPanel, tr("帧列表"));

    auto *timelinePanel = new QWidget;
    auto *timelineLayout = new QVBoxLayout(timelinePanel);
    timelineLayout->setContentsMargins(8, 8, 8, 8);
    timelineLayout->setSpacing(6);
    auto *timelineTools = new QHBoxLayout;
    auto *zoomInButton = commandButton(tr("放大"));
    auto *zoomOutButton = commandButton(tr("缩小"));
    auto *panLeftButton = commandButton(tr("向左"));
    auto *panRightButton = commandButton(tr("向右"));
    auto *previousAnomalyButton = commandButton(tr("上一异常"));
    auto *nextAnomalyButton = commandButton(tr("下一异常"));
    auto *resetTimelineButton = commandButton(tr("全部"));
    auto *timelineRange = new QLabel(tr("无时间线数据"));
    timelineRange->setObjectName("sectionHint");
    timelineTools->addWidget(zoomInButton);
    timelineTools->addWidget(zoomOutButton);
    timelineTools->addWidget(panLeftButton);
    timelineTools->addWidget(panRightButton);
    timelineTools->addWidget(previousAnomalyButton);
    timelineTools->addWidget(nextAnomalyButton);
    timelineTools->addWidget(resetTimelineButton);
    timelineTools->addWidget(timelineRange, 1);
    timelineLayout->addLayout(timelineTools);
    m_timeline = new TimelineWidget;
    timelineLayout->addWidget(m_timeline, 1);
    connect(zoomInButton, &QPushButton::clicked, m_timeline, [this] { m_timeline->zoomBy(0.7); });
    connect(zoomOutButton, &QPushButton::clicked, m_timeline, [this] { m_timeline->zoomBy(1.4); });
    connect(panLeftButton, &QPushButton::clicked, m_timeline, [this] { m_timeline->panBy(-1); });
    connect(panRightButton, &QPushButton::clicked, m_timeline, [this] { m_timeline->panBy(1); });
    connect(previousAnomalyButton, &QPushButton::clicked, m_timeline, [this] { m_timeline->navigateAnomaly(-1); });
    connect(nextAnomalyButton, &QPushButton::clicked, m_timeline, [this] { m_timeline->navigateAnomaly(1); });
    connect(resetTimelineButton, &QPushButton::clicked, m_timeline, &TimelineWidget::resetView);
    connect(m_timeline, &TimelineWidget::rangeChanged, timelineRange, &QLabel::setText);
    connect(m_timeline, &TimelineWidget::frameSelected, this, [this](int row) {
        if (row < 0 || row >= m_framesTable->rowCount()) return;
        m_framesTable->selectRow(row);
        m_framesTable->scrollToItem(m_framesTable->item(row, 0));
    });
    connect(m_timeline, &TimelineWidget::frameActivated, this, [this](int row) {
        if (row < 0 || row >= m_framesTable->rowCount()) return;
        m_framesTable->selectRow(row);
        m_tabs->setCurrentWidget(m_framesPanel);
    });
    m_tabs->addTab(timelinePanel, tr("时间线"));

    m_preview = new MediaPreviewWidget;
    connect(m_preview, &MediaPreviewWidget::stepRequested, this, &MainWindow::stepMediaPreview);
    m_tabs->addTab(m_preview, tr("媒体预览"));

    m_streamsTable = readOnlyTable();
    m_streamsTable->setColumnCount(11);
    m_streamsTable->setHorizontalHeaderLabels({"#", tr("类型"), tr("编码"), "Profile", tr("画面 / 声道"),
        tr("采样率"), tr("帧率"), "Time Base", tr("时长"), tr("码率"), tr("格式")});
    m_streamsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_streamsTable->setAlternatingRowColors(true);
    m_streamsTable->verticalHeader()->hide();
    m_streamsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_streamsTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    connect(m_streamsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item ? item->data(OffsetRole).toLongLong() : -1;
        if (offset >= 0) {
            showHex(offset, 1);
            m_tabs->setCurrentWidget(m_hexPanel);
        }
    });
    m_tabs->addTab(m_streamsTable, tr("媒体流"));

    auto *bookmarkPanel = new QWidget;
    auto *bookmarkLayout = new QVBoxLayout(bookmarkPanel);
    bookmarkLayout->setContentsMargins(8, 8, 8, 8);
    bookmarkLayout->setSpacing(7);
    auto *bookmarkTools = new QHBoxLayout;
    auto *addBookmarkButton = commandButton("+");
    auto *removeBookmarkButton = commandButton("-");
    addBookmarkButton->setFixedWidth(36);
    removeBookmarkButton->setFixedWidth(36);
    addBookmarkButton->setToolTip(tr("添加当前 Offset 书签"));
    removeBookmarkButton->setToolTip(tr("删除选中书签"));
    connect(addBookmarkButton, &QPushButton::clicked, this, &MainWindow::addBookmark);
    connect(removeBookmarkButton, &QPushButton::clicked, this, &MainWindow::removeBookmark);
    bookmarkTools->addWidget(addBookmarkButton);
    bookmarkTools->addWidget(removeBookmarkButton);
    bookmarkTools->addStretch();
    bookmarkLayout->addLayout(bookmarkTools);
    m_bookmarksTable = readOnlyTable();
    m_bookmarksTable->setColumnCount(3);
    m_bookmarksTable->setHorizontalHeaderLabels({"Offset", tr("备注"), tr("位置")});
    m_bookmarksTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_bookmarksTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_bookmarksTable->setAlternatingRowColors(true);
    m_bookmarksTable->verticalHeader()->hide();
    m_bookmarksTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_bookmarksTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_bookmarksTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    connect(m_bookmarksTable, &QTableWidget::itemDoubleClicked, this, &MainWindow::onBookmarkActivated);
    bookmarkLayout->addWidget(m_bookmarksTable);
    m_tabs->addTab(bookmarkPanel, tr("书签"));

    m_hexCompare = new HexCompareWidget;
    m_tabs->addTab(m_hexCompare, tr("双栏 Hex 对比"));

    m_compareTree = new QTreeWidget;
    m_compareTree->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_compareTree->setColumnCount(5);
    m_compareTree->setHeaderLabels({tr("状态"), tr("对象"), tr("属性"), tr("左侧"), tr("右侧")});
    m_compareTree->setAlternatingRowColors(true);
    m_compareTree->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_compareTree->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_compareTree->header()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_compareTree->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    m_compareTree->header()->setSectionResizeMode(3, QHeaderView::Stretch);
    m_compareTree->header()->setSectionResizeMode(4, QHeaderView::Stretch);
    connect(m_compareTree, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem *item) {
        const qint64 offset = item->data(0, OffsetRole).toLongLong();
        if (offset >= 0) { showHex(offset, 1); m_tabs->setCurrentWidget(m_hexPanel); }
    });
    m_tabs->addTab(m_compareTree, tr("结构对比"));

    m_transportPanel = new QWidget;
    auto *transportLayout = new QVBoxLayout(m_transportPanel);
    transportLayout->setContentsMargins(10, 10, 10, 10);
    transportLayout->setSpacing(8);
    auto *transportTools = new QHBoxLayout;
    m_transportSummary = new QLabel(tr("当前文件没有 RTP 传输会话"));
    m_transportSummary->setObjectName("sectionHint");
    m_transportSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    m_transportIssuesOnly = new QCheckBox(tr("只看异常会话"));
    connect(m_transportIssuesOnly, &QCheckBox::toggled, this, [this] { filterTransportSessions(); });
    transportTools->addWidget(m_transportSummary, 1);
    transportTools->addWidget(m_transportIssuesOnly);
    transportLayout->addLayout(transportTools);
    m_transportSessionsTable = readOnlyTable();
    m_transportSessionsTable->setColumnCount(15);
    m_transportSessionsTable->setHorizontalHeaderLabels({
        tr("状态"), tr("端点"), "SSRC", "PT", tr("包"), "Payload", tr("序号范围"),
        tr("估算丢失"), tr("重复"), tr("乱序"), "Marker", tr("码率"), "RTCP", "Jitter", "DLSR"
    });
    m_transportSessionsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_transportSessionsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_transportSessionsTable->setAlternatingRowColors(true);
    m_transportSessionsTable->setSortingEnabled(true);
    m_transportSessionsTable->verticalHeader()->hide();
    m_transportSessionsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_transportSessionsTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    connect(m_transportSessionsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 12);
        m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("传输会话首包  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    m_transportDetails = new QTabWidget;
    m_transportDetails->setDocumentMode(true);
    m_transportDetails->tabBar()->setUsesScrollButtons(false);
    m_transportDetails->tabBar()->setElideMode(Qt::ElideRight);
    m_transportDetails->addTab(m_transportSessionsTable, tr("会话质量"));

    auto *videoPayloadPanel = new QWidget;
    auto *videoPayloadLayout = new QVBoxLayout(videoPayloadPanel);
    videoPayloadLayout->setContentsMargins(8, 8, 8, 8);
    videoPayloadLayout->setSpacing(7);
    m_rtpVideoSummary = new QLabel(tr("当前文件没有可识别的 RTP H.264/H.265 视频负载"));
    m_rtpVideoSummary->setObjectName("sectionHint");
    m_rtpVideoSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    videoPayloadLayout->addWidget(m_rtpVideoSummary);
    m_rtpVideoStreamsTable = readOnlyTable();
    m_rtpVideoStreamsTable->setColumnCount(8);
    m_rtpVideoStreamsTable->setHorizontalHeaderLabels({
        tr("状态"), tr("编码"), "SSRC", "Packetization", tr("NALU 类型"),
        tr("包 / NALU"), tr("完成 / 未完成"), tr("问题")
    });
    m_rtpVideoStreamsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rtpVideoStreamsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rtpVideoStreamsTable->setAlternatingRowColors(true);
    m_rtpVideoStreamsTable->setSortingEnabled(true);
    m_rtpVideoStreamsTable->verticalHeader()->hide();
    m_rtpVideoStreamsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_rtpVideoStreamsTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    m_rtpVideoStreamsTable->horizontalHeader()->setSectionResizeMode(4, QHeaderView::Stretch);
    connect(m_rtpVideoStreamsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 12);
        m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("RTP 视频负载  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    videoPayloadLayout->addWidget(m_rtpVideoStreamsTable, 1);
    m_transportDetails->addTab(videoPayloadPanel, tr("视频负载"));

    m_rtpVideoIssuesTable = readOnlyTable();
    m_rtpVideoIssuesTable->setColumnCount(3);
    m_rtpVideoIssuesTable->setHorizontalHeaderLabels({tr("状态"), "Offset", tr("问题")});
    m_rtpVideoIssuesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rtpVideoIssuesTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rtpVideoIssuesTable->setAlternatingRowColors(true);
    m_rtpVideoIssuesTable->verticalHeader()->hide();
    m_rtpVideoIssuesTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_rtpVideoIssuesTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_rtpVideoIssuesTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    connect(m_rtpVideoIssuesTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 8);
        m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("RTP 视频负载问题  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    m_transportDetails->addTab(m_rtpVideoIssuesTable, tr("负载问题"));

    auto *signalingPanel = new QWidget;
    auto *signalingLayout = new QVBoxLayout(signalingPanel);
    signalingLayout->setContentsMargins(8, 8, 8, 8);
    signalingLayout->setSpacing(7);
    m_sipSdpSummary = new QLabel(tr("当前文件没有 SIP/SDP 信令"));
    m_sipSdpSummary->setObjectName("sectionHint");
    m_sipSdpSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    signalingLayout->addWidget(m_sipSdpSummary);
    auto *signalingSplitter = new QSplitter(Qt::Vertical);
    m_sipMessagesTable = readOnlyTable();
    m_sipMessagesTable->setColumnCount(8);
    m_sipMessagesTable->setHorizontalHeaderLabels({
        "#", tr("类型"), tr("方法 / 状态"), "Call-ID", "CSeq", tr("源 -> 目的"), "SDP", "Offset"
    });
    m_sipMessagesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_sipMessagesTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_sipMessagesTable->setAlternatingRowColors(true);
    m_sipMessagesTable->verticalHeader()->hide();
    m_sipMessagesTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_sipMessagesTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    m_sipMessagesTable->horizontalHeader()->setSectionResizeMode(5, QHeaderView::Stretch);
    connect(m_sipMessagesTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 32);
        m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("SIP 信令  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    signalingSplitter->addWidget(m_sipMessagesTable);
    m_sdpMappingsTable = readOnlyTable();
    m_sdpMappingsTable->setColumnCount(9);
    m_sdpMappingsTable->setHorizontalHeaderLabels({
        "Call-ID", tr("媒体"), tr("地址 : 端口"), "PT", tr("编码"), "Clock", tr("声道"), tr("方向"), "FMTP"
    });
    m_sdpMappingsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_sdpMappingsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_sdpMappingsTable->setAlternatingRowColors(true);
    m_sdpMappingsTable->verticalHeader()->hide();
    m_sdpMappingsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_sdpMappingsTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    m_sdpMappingsTable->horizontalHeader()->setSectionResizeMode(8, QHeaderView::Stretch);
    connect(m_sdpMappingsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 32);
        m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("SDP 媒体协商  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    signalingSplitter->addWidget(m_sdpMappingsTable);
    signalingSplitter->setSizes({260, 300});
    signalingLayout->addWidget(signalingSplitter, 1);
    m_transportDetails->addTab(signalingPanel, tr("信令协商"));

    auto *feedbackPanel = new QWidget;
    auto *feedbackLayout = new QVBoxLayout(feedbackPanel);
    feedbackLayout->setContentsMargins(8, 8, 8, 8);
    feedbackLayout->setSpacing(7);
    m_rtcpFeedbackSummary = new QLabel(tr("当前文件没有 RTCP 控制反馈"));
    m_rtcpFeedbackSummary->setObjectName("sectionHint");
    m_rtcpFeedbackSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    feedbackLayout->addWidget(m_rtcpFeedbackSummary);
    auto *feedbackSplitter = new QSplitter(Qt::Vertical);
    m_rtcpFeedbackTable = readOnlyTable();
    m_rtcpFeedbackTable->setColumnCount(6);
    m_rtcpFeedbackTable->setHorizontalHeaderLabels({tr("类型"), tr("发送者 SSRC"), tr("媒体 SSRC"), tr("详情"), "FMT", "Offset"});
    m_rtcpFeedbackTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rtcpFeedbackTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rtcpFeedbackTable->setAlternatingRowColors(true);
    m_rtcpFeedbackTable->verticalHeader()->hide();
    m_rtcpFeedbackTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_rtcpFeedbackTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    connect(m_rtcpFeedbackTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 16); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("RTCP 控制反馈  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    feedbackSplitter->addWidget(m_rtcpFeedbackTable);
    m_rtcpMetadataTable = readOnlyTable();
    m_rtcpMetadataTable->setColumnCount(4);
    m_rtcpMetadataTable->setHorizontalHeaderLabels({tr("类型"), "SSRC", tr("CNAME / 结束原因"), "Offset"});
    m_rtcpMetadataTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rtcpMetadataTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rtcpMetadataTable->setAlternatingRowColors(true);
    m_rtcpMetadataTable->verticalHeader()->hide();
    m_rtcpMetadataTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_rtcpMetadataTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    connect(m_rtcpMetadataTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 16); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("RTCP 会话事件  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    feedbackSplitter->addWidget(m_rtcpMetadataTable);
    feedbackSplitter->setSizes({340, 190});
    feedbackLayout->addWidget(feedbackSplitter, 1);
    m_transportDetails->addTab(feedbackPanel, tr("控制反馈"));

    auto *timingPanel = new QWidget;
    auto *timingLayout = new QVBoxLayout(timingPanel);
    timingLayout->setContentsMargins(8, 8, 8, 8);
    timingLayout->setSpacing(7);
    m_rtpTimingSummary = new QLabel(tr("当前文件没有可计算的 RTP 时序质量"));
    m_rtpTimingSummary->setObjectName("sectionHint");
    m_rtpTimingSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    timingLayout->addWidget(m_rtpTimingSummary);
    auto *timingSplitter = new QSplitter(Qt::Vertical);
    m_rtpTimingTable = readOnlyTable();
    m_rtpTimingTable->setColumnCount(10);
    m_rtpTimingTable->setHorizontalHeaderLabels({
        tr("状态"), tr("端点"), "SSRC", tr("Clock"), tr("包"), tr("RFC 3550 Jitter"),
        tr("平均间隔"), tr("间隔范围"), tr("最大偏差"), tr("突发")
    });
    m_rtpTimingTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rtpTimingTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rtpTimingTable->setAlternatingRowColors(true);
    m_rtpTimingTable->setSortingEnabled(true);
    m_rtpTimingTable->verticalHeader()->hide();
    m_rtpTimingTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_rtpTimingTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    connect(m_rtpTimingTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 12); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("RTP 时序会话  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    timingSplitter->addWidget(m_rtpTimingTable);
    m_rtpTimingEventsTable = readOnlyTable();
    m_rtpTimingEventsTable->setColumnCount(7);
    m_rtpTimingEventsTable->setHorizontalHeaderLabels({
        "SSRC", tr("序号"), tr("到达间隔"), tr("媒体间隔"), tr("偏差"), tr("阈值"), "Offset"
    });
    m_rtpTimingEventsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rtpTimingEventsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rtpTimingEventsTable->setAlternatingRowColors(true);
    m_rtpTimingEventsTable->verticalHeader()->hide();
    m_rtpTimingEventsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_rtpTimingEventsTable->horizontalHeader()->setSectionResizeMode(4, QHeaderView::Stretch);
    connect(m_rtpTimingEventsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 12); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("RTP 突发延迟  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    timingSplitter->addWidget(m_rtpTimingEventsTable);
    timingSplitter->setSizes({340, 190});
    timingLayout->addWidget(timingSplitter, 1);
    m_transportDetails->addTab(timingPanel, tr("时序质量"));

    auto *twccPanel = new QWidget;
    auto *twccLayout = new QVBoxLayout(twccPanel);
    twccLayout->setContentsMargins(8, 8, 8, 8);
    twccLayout->setSpacing(7);
    m_twccSummary = new QLabel(tr("当前文件没有 TWCC / REMB 拥塞反馈"));
    m_twccSummary->setObjectName("sectionHint");
    m_twccSummary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    twccLayout->addWidget(m_twccSummary);
    auto *twccSplitter = new QSplitter(Qt::Vertical);
    m_twccFeedbackTable = readOnlyTable();
    m_twccFeedbackTable->setColumnCount(9);
    m_twccFeedbackTable->setHorizontalHeaderLabels({
        tr("媒体 SSRC"), tr("Base Sequence"), tr("状态数"), tr("收到"), tr("丢失"),
        tr("参考时间"), tr("反馈计数"), tr("最大 Delta"), "Offset"
    });
    m_twccFeedbackTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_twccFeedbackTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_twccFeedbackTable->setAlternatingRowColors(true);
    m_twccFeedbackTable->verticalHeader()->hide();
    m_twccFeedbackTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_twccFeedbackTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    connect(m_twccFeedbackTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 28); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("TWCC 拥塞反馈  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    twccSplitter->addWidget(m_twccFeedbackTable);
    m_twccPacketsTable = readOnlyTable();
    m_twccPacketsTable->setColumnCount(7);
    m_twccPacketsTable->setHorizontalHeaderLabels({tr("序号"), tr("状态"), tr("收到"), tr("Delta"), tr("接收时间"), tr("Delta 字节"), "Offset"});
    m_twccPacketsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_twccPacketsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_twccPacketsTable->setAlternatingRowColors(true);
    m_twccPacketsTable->verticalHeader()->hide();
    m_twccPacketsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_twccPacketsTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    connect(m_twccPacketsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 2); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("TWCC 包状态  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    twccSplitter->addWidget(m_twccPacketsTable);
    m_rembTable = readOnlyTable();
    m_rembTable->setColumnCount(8);
    m_rembTable->setHorizontalHeaderLabels({
        tr("发送者 SSRC"), tr("目标 SSRC"), tr("码率"), tr("指数"), tr("尾数"), tr("目标数"), tr("媒体 SSRC"), "Offset"
    });
    m_rembTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rembTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_rembTable->setAlternatingRowColors(true);
    m_rembTable->verticalHeader()->hide();
    m_rembTable->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    m_rembTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    connect(m_rembTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 24); m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("REMB 带宽估计  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    twccSplitter->addWidget(m_rembTable);
    twccSplitter->setSizes({210, 250, 170});
    twccLayout->addWidget(twccSplitter, 1);
    m_transportDetails->addTab(twccPanel, tr("拥塞反馈"));
    transportLayout->addWidget(m_transportDetails, 1);
    m_tabs->addTab(m_transportPanel, tr("传输会话"));

    m_codecHealthPanel = new QWidget;
    auto *codecHealthLayout = new QVBoxLayout(m_codecHealthPanel);
    codecHealthLayout->setContentsMargins(10, 10, 10, 10);
    codecHealthLayout->setSpacing(10);
    auto *codecMetrics = new QGridLayout;
    codecMetrics->setSpacing(8);
    codecMetrics->addWidget(makeMetricCard(tr("编码"), &m_codecMetric, "#2F91C7"), 0, 0);
    codecMetrics->addWidget(makeMetricCard(tr("健康状态"), &m_codecStatusMetric, "#34B58A"), 0, 1);
    codecMetrics->addWidget(makeMetricCard(tr("参数集"), &m_codecParameterMetric, "#8A74D6"), 0, 2);
    codecMetrics->addWidget(makeMetricCard(tr("Slice / 关键帧"), &m_codecSliceMetric, "#D08A3E"), 1, 0);
    codecMetrics->addWidget(makeMetricCard(tr("问题"), &m_codecIssueMetric, "#D35D6E"), 1, 1);
    codecMetrics->addWidget(makeMetricCard(tr("分辨率变化"), &m_codecResolutionMetric, "#4E9EAD"), 1, 2);
    codecHealthLayout->addLayout(codecMetrics);

    auto *codecDetails = new QTabWidget;
    codecDetails->setDocumentMode(true);
    codecDetails->tabBar()->setUsesScrollButtons(false);
    codecDetails->tabBar()->setElideMode(Qt::ElideRight);
    m_codecIssuesTable = readOnlyTable();
    m_codecIssuesTable->setColumnCount(4);
    m_codecIssuesTable->setHorizontalHeaderLabels({tr("状态"), "Offset", tr("问题"), tr("来源")});
    m_codecIssuesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_codecIssuesTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_codecIssuesTable->setAlternatingRowColors(true);
    m_codecIssuesTable->verticalHeader()->hide();
    m_codecIssuesTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_codecIssuesTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_codecIssuesTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_codecIssuesTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    connect(m_codecIssuesTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 8);
        m_tabs->setCurrentWidget(m_hexPanel);
        m_statusText->setText(tr("码流问题定位  |  Offset 0x%1").arg(offset, 0, 16).toUpper());
    });
    codecDetails->addTab(m_codecIssuesTable, tr("问题"));

    m_codecParametersTable = readOnlyTable();
    m_codecParametersTable->setColumnCount(5);
    m_codecParametersTable->setHorizontalHeaderLabels({tr("集合"), tr("数量"), tr("定义 / 引用 ID"), tr("缺失 ID"), tr("状态")});
    m_codecParametersTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_codecParametersTable->setAlternatingRowColors(true);
    m_codecParametersTable->verticalHeader()->hide();
    m_codecParametersTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_codecParametersTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_codecParametersTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_codecParametersTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    m_codecParametersTable->horizontalHeader()->setSectionResizeMode(4, QHeaderView::ResizeToContents);
    codecDetails->addTab(m_codecParametersTable, tr("参数集引用"));

    m_codecResolutionsTable = readOnlyTable();
    m_codecResolutionsTable->setColumnCount(5);
    m_codecResolutionsTable->setHorizontalHeaderLabels({tr("SPS ID"), tr("宽"), tr("高"), "Offset", tr("事件")});
    m_codecResolutionsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_codecResolutionsTable->setAlternatingRowColors(true);
    m_codecResolutionsTable->verticalHeader()->hide();
    m_codecResolutionsTable->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
    connect(m_codecResolutionsTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *item) {
        const qint64 offset = item->data(OffsetRole).toLongLong();
        showHex(offset, 8);
        m_tabs->setCurrentWidget(m_hexPanel);
    });
    codecDetails->addTab(m_codecResolutionsTable, tr("分辨率事件"));
    codecHealthLayout->addWidget(codecDetails, 1);
    m_tabs->addTab(m_codecHealthPanel, tr("码流健康"));
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
    m_selectionDetails->setToolTip(tr("选中文本后按 Ctrl+C 复制"));
    layout->addWidget(m_selectionDetails);
    layout->addWidget(sectionLabel(tr("全局诊断")));
    auto *hint = new QLabel(tr("warning / error 与媒体探测摘要"));
    hint->setObjectName("sectionHint");
    layout->addWidget(hint);
    auto *diagnosticTools = new QWidget;
    auto *diagnosticLayout = new QHBoxLayout(diagnosticTools);
    diagnosticLayout->setContentsMargins(0, 0, 0, 0);
    diagnosticLayout->setSpacing(5);
    m_diagnosticSeverityFilter = new QComboBox;
    m_diagnosticSeverityFilter->addItem(tr("全部级别"), "all");
    m_diagnosticSeverityFilter->addItem(tr("仅 Warning"), "warning");
    m_diagnosticSeverityFilter->addItem(tr("仅 Error"), "error");
    m_diagnosticSeverityFilter->setToolTip(tr("按诊断级别筛选"));
    m_diagnosticSourceFilter = new QComboBox;
    m_diagnosticSourceFilter->addItem(tr("全部来源"), "all");
    m_diagnosticSourceFilter->setToolTip(tr("按诊断来源筛选"));
    m_diagnosticOffsetOnly = new QCheckBox(tr("有 Offset"));
    m_diagnosticOffsetOnly->setToolTip(tr("仅显示可以定位到 Hex 的诊断"));
    m_diagnosticSummary = new QLabel;
    m_diagnosticSummary->setObjectName("sectionHint");
    diagnosticLayout->addWidget(m_diagnosticSeverityFilter, 1);
    diagnosticLayout->addWidget(m_diagnosticSourceFilter, 1);
    diagnosticLayout->addWidget(m_diagnosticOffsetOnly);
    diagnosticLayout->addWidget(m_diagnosticSummary);
    connect(m_diagnosticSeverityFilter, &QComboBox::currentIndexChanged, this, [this] { filterDiagnostics(); });
    connect(m_diagnosticSourceFilter, &QComboBox::currentIndexChanged, this, [this] { filterDiagnostics(); });
    connect(m_diagnosticOffsetOnly, &QCheckBox::toggled, this, [this] { filterDiagnostics(); });
    layout->addWidget(diagnosticTools);
    m_diagnosticsTable = readOnlyTable();
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
    m_diagnosticsTable->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(m_diagnosticsTable, &QTableWidget::customContextMenuRequested, this, [this](const QPoint &position) {
        const auto *item = m_diagnosticsTable->itemAt(position);
        if (!item) return;
        const qint64 offset = item->data(OffsetRole).toLongLong();
        if (offset < 0) return;
        m_diagnosticsTable->selectRow(item->row());
        showHex(offset, 1);
        QMenu menu(this);
        menu.addAction(tr("添加当前诊断为书签"), this, [this, row = item->row(), offset] {
            const QString source = m_diagnosticsTable->item(row, 1)->text();
            const QString message = m_diagnosticsTable->item(row, 3)->text();
            m_bookmarks.append(QJsonObject{{"offset", offset}, {"note", message}, {"location", source}});
            populateBookmarks();
            m_statusText->setText(tr("诊断已加入书签：0x%1").arg(offset, 0, 16).toUpper());
        });
        menu.exec(m_diagnosticsTable->viewport()->mapToGlobal(position));
    });
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
    auto *cancel = fileMenu->addAction(tr("取消当前任务"), QKeySequence(Qt::Key_Escape));
    connect(cancel, &QAction::triggered, this, &MainWindow::cancelAnalysis);
    m_recentMenu = fileMenu->addMenu(tr("最近文件"));
    rebuildRecentMenu();
    fileMenu->addSeparator();
    auto *html = fileMenu->addAction(tr("导出 HTML 报告..."));
    connect(html, &QAction::triggered, this, &MainWindow::exportHtml);
    auto *json = fileMenu->addAction(tr("导出 JSON 报告..."));
    connect(json, &QAction::triggered, this, &MainWindow::exportJson);
    fileMenu->addSeparator();
    auto *snapshot = fileMenu->addAction(tr("保存工程快照..."), QKeySequence::Save);
    connect(snapshot, &QAction::triggered, this, &MainWindow::saveProjectSnapshot);
    fileMenu->addSeparator();
    fileMenu->addAction(tr("退出"), qApp, &QApplication::quit);

    auto *compareMenu = menuBar()->addMenu(tr("对比"));
    compareMenu->addAction(tr("二进制对比..."), this, &MainWindow::compareBinary);
    compareMenu->addAction(tr("协议结构对比..."), this, &MainWindow::compareProtocol);
    compareMenu->addAction(tr("帧级对比..."), this, &MainWindow::compareFrames);

    auto *viewMenu = menuBar()->addMenu(tr("视图"));
    auto *toolbarMenu = viewMenu->addMenu(tr("功能栏"));
    for (int index = 0; index < m_tabs->count(); ++index) {
        const QString title = m_tabs->tabText(index);
        auto *action = toolbarMenu->addAction(title);
        action->setCheckable(true);
        const QString key = QString("view/tabVisible/%1").arg(index);
        const bool visible = m_settings.value(key, true).toBool();
        m_tabs->setTabVisible(index, visible);
        action->setChecked(visible);
        connect(action, &QAction::toggled, this, [this, action, index, key](bool checked) {
            int visibleCount = 0;
            for (int tab = 0; tab < m_tabs->count(); ++tab)
                visibleCount += m_tabs->isTabVisible(tab) ? 1 : 0;
            if (!checked && visibleCount == 1) {
                QSignalBlocker blocker(action);
                action->setChecked(true);
                return;
            }
            m_tabs->setTabVisible(index, checked);
            if (!checked && m_tabs->currentIndex() == index) {
                for (int tab = 0; tab < m_tabs->count(); ++tab) {
                    if (m_tabs->isTabVisible(tab)) {
                        m_tabs->setCurrentIndex(tab);
                        break;
                    }
                }
            }
            m_settings.setValue(key, checked);
            m_settings.sync();
        });
    }
    viewMenu->addSeparator();
    auto *themeMenu = viewMenu->addMenu(tr("主题"));
    auto *themes = new QActionGroup(this);
    m_darkThemeAction = themeMenu->addAction(tr("夜间主题"));
    m_lightThemeAction = themeMenu->addAction(tr("浅色主题"));
    m_darkThemeAction->setCheckable(true);
    m_lightThemeAction->setCheckable(true);
    themes->addAction(m_darkThemeAction);
    themes->addAction(m_lightThemeAction);
    connect(m_darkThemeAction, &QAction::triggered, this, &MainWindow::setDarkTheme);
    connect(m_lightThemeAction, &QAction::triggered, this, &MainWindow::setLightTheme);
    viewMenu->addSeparator();
    auto *hexMenu = viewMenu->addMenu(tr("Hex 显示"));
    hexMenu->addAction(tr("切换字节 / 整行高亮"), QKeySequence("Ctrl+Shift+L"), this, [this] {
        if (m_tabs->currentWidget() != m_hexPanel)
            return;
        m_hexFullLineSelection = !m_hexFullLineSelection;
        renderHexPage(m_hexPageStart, m_hexOffset, m_hexFocusSize);
        m_statusText->setText(m_hexFullLineSelection
            ? tr("Hex 已切换为整行高亮（Ctrl+Shift+L 恢复仅高亮字节）")
            : tr("Hex 已切换为仅高亮对应字节（Ctrl+Shift+L 切换整行）"));
    });
    auto *treeMenu = viewMenu->addMenu(tr("协议树"));
    treeMenu->addAction(tr("展开全部"), QKeySequence("Ctrl+Shift+E"), m_protocolTree, &QTreeWidget::expandAll);
    treeMenu->addAction(tr("折叠全部"), QKeySequence("Ctrl+Shift+C"), m_protocolTree, &QTreeWidget::collapseAll);

    auto *editMenu = menuBar()->addMenu(tr("编辑"));
    editMenu->addAction(tr("跳转到 Offset..."), QKeySequence("Ctrl+G"), this, &MainWindow::jumpToOffset);
    editMenu->addSeparator();
    editMenu->addAction(tr("复制当前 Offset"), QKeySequence("Ctrl+Shift+O"), this, &MainWindow::copyCurrentOffset);
    editMenu->addAction(tr("复制当前值"), QKeySequence::Copy, this, &MainWindow::copyCurrentValue);
    editMenu->addAction(tr("复制文件完整路径"), QKeySequence("Ctrl+Alt+C"), this, &MainWindow::copyCurrentPath);
    editMenu->addSeparator();
    editMenu->addAction(tr("添加 Offset 书签..."), QKeySequence("Ctrl+B"), this, &MainWindow::addBookmark);
    editMenu->addAction(tr("删除选中书签"), this, &MainWindow::removeBookmark);

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
    auto *findNext = new QShortcut(QKeySequence(Qt::Key_F3), this);
    connect(findNext, &QShortcut::activated, this, &MainWindow::searchNext);
    for (int index = 0; index < 9; ++index) {
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
        applyTheme(m_settings.value("theme", "dark").toString() != "light", false);
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    if (m_process->state() != QProcess::NotRunning) {
        m_cancelRequested = true;
        m_process->kill();
    }
    m_settings.setValue("windowGeometry", saveGeometry());
    m_settings.setValue("splitterState", m_mainSplitter->saveState());
    m_settings.setValue("currentTab", m_tabs->currentIndex());
    m_settings.sync();
    QMainWindow::closeEvent(event);
}

void MainWindow::chooseFile()
{
    const auto path = QFileDialog::getOpenFileName(this, tr("打开音视频或协议文件"), QDir(QCoreApplication::applicationDirPath()).filePath("samples"));
    if (!path.isEmpty())
        openPath(path);
}

void MainWindow::reloadCurrent()
{
    if (!m_currentProjectPath.isEmpty())
        loadProjectSnapshot(m_currentProjectPath);
    else if (!m_currentPath.isEmpty())
        openPath(m_currentPath);
}

void MainWindow::cancelAnalysis()
{
    if (m_process->state() == QProcess::NotRunning)
        return;
    m_cancelRequested = true;
    m_statusText->setText(tr("正在取消任务..."));
    m_process->terminate();
    QTimer::singleShot(1200, m_process, [this] {
        if (m_process->state() != QProcess::NotRunning) m_process->kill();
    });
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
    if (info.fileName().endsWith(".avscope.json", Qt::CaseInsensitive)) {
        loadProjectSnapshot(info.absoluteFilePath());
        return;
    }

    bool rawAccepted = true;
    const QStringList rawOptions = rawOptionsForPath(info.absoluteFilePath(), &rawAccepted);
    if (!rawAccepted) return;

    m_currentPath = info.absoluteFilePath();
    m_currentProjectPath.clear();
    m_currentRawOptions = rawOptions;
    m_previewPosition = 0.0;
    m_previewFrame = 0;
    m_bookmarks = {};
    populateBookmarks();
    m_cancelRequested = false;
    QDir().mkpath(projectRoot() + "/tmp/qt-runtime");
    QFile::remove(analysisOutputPath());
    m_fileLabel->setText(info.fileName());
    m_statusText->setText(tr("正在分析 %1...").arg(info.fileName()));
    m_log->appendPlainText(tr("[%1] 开始分析 %2").arg(QTime::currentTime().toString("HH:mm:ss"), m_currentPath));

    QStringList arguments = {"analyze", m_currentPath, "--json", analysisOutputPath()};
    arguments.append(m_currentRawOptions);
    arguments << "--preview-dir" << projectRoot() + "/tmp/qt-previews"
              << "--preview-position" << QString::number(m_previewPosition)
              << "--preview-frame" << QString::number(m_previewFrame);
    startEngineTask("analysis", arguments);
}

bool MainWindow::loadProjectSnapshot(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        QMessageBox::critical(this, tr("工程快照读取失败"), file.errorString());
        return false;
    }
    QJsonParseError error;
    const auto snapshot = QJsonDocument::fromJson(file.readAll(), &error).object();
    const auto analysis = snapshot.value("analysis").toObject();
    if (analysis.isEmpty() || !analysis.contains("media") || !analysis.contains("root")) {
        QMessageBox::critical(this, tr("工程快照无效"), error.errorString().isEmpty() ? tr("缺少 analysis/media/root 数据。") : error.errorString());
        return false;
    }
    m_currentProjectPath = path;
    m_currentPath = snapshot.value("source_path").toString(analysis.value("media").toObject().value("path").toString());
    m_currentRawOptions.clear();
    for (const auto &value : snapshot.value("raw_options").toArray()) m_currentRawOptions << value.toString();
    m_bookmarks = snapshot.value("bookmarks").toArray();
    populateBookmarks();
    m_previewPosition = analysis.value("media").toObject().value("summary").toObject()
        .value("video_preview").toObject().value("position_seconds").toDouble();
    m_previewFrame = analysis.value("media").toObject().value("summary").toObject()
        .value("yuv_preview").toObject().value("frame_index").toInt();
    loadDocument(QJsonDocument(analysis));
    const int tab = snapshot.value("current_tab").toInt(m_tabs->currentIndex());
    m_tabs->setCurrentIndex(qBound(0, tab, m_tabs->count() - 1));
    if (snapshot.value("theme").toString() == "light") applyTheme(false);
    else if (snapshot.value("theme").toString() == "dark") applyTheme(true);
    m_fileLabel->setText(QFileInfo(path).completeBaseName());
    m_fileLabel->setToolTip(path);
    m_statusText->setText(QFileInfo::exists(m_currentPath)
        ? tr("工程快照已恢复：%1").arg(QFileInfo(path).fileName())
        : tr("工程快照已恢复，源文件已移动：%1").arg(m_currentPath));
    m_log->appendPlainText(tr("[%1] 恢复工程快照 %2").arg(QTime::currentTime().toString("HH:mm:ss"), path));
    addRecentFile(path);
    return true;
}

void MainWindow::stepMediaPreview(int direction)
{
    if (m_currentPath.isEmpty() || !QFileInfo::exists(m_currentPath)) {
        QMessageBox::information(this, tr("无法刷新预览"), tr("工程源文件不存在，无法生成新的预览位置。"));
        return;
    }
    const auto summary = m_document.object().value("media").toObject().value("summary").toObject();
    if (summary.contains("yuv_preview")) {
        const int total = summary.value("yuv_preview").toObject().value("total_frames").toInt();
        m_previewFrame = qBound(0, m_previewFrame + direction, qMax(0, total - 1));
        m_statusText->setText(tr("正在生成 Raw YUV 第 %1 帧...").arg(m_previewFrame + 1));
    } else {
        m_previewPosition = qMax(0.0, m_previewPosition + direction * 1.0);
        m_statusText->setText(tr("正在生成 %1 秒视频预览...").arg(m_previewPosition, 0, 'f', 3));
    }
    QStringList arguments = {"analyze", m_currentPath, "--json", analysisOutputPath()};
    arguments.append(m_currentRawOptions);
    arguments << "--preview-dir" << projectRoot() + "/tmp/qt-previews"
              << "--preview-position" << QString::number(m_previewPosition)
              << "--preview-frame" << QString::number(m_previewFrame);
    startEngineTask("analysis", arguments);
}

QStringList MainWindow::rawOptionsForPath(const QString &path, bool *accepted)
{
    *accepted = true;
    const QString suffix = QFileInfo(path).suffix().toLower();
    if (suffix != "pcm" && suffix != "yuv") return {};
    if (suffix == "pcm" && !qEnvironmentVariableIsEmpty("AVSCOPE_RAW_SAMPLE_RATE")) {
        QStringList preset = {"--sample-rate", qEnvironmentVariable("AVSCOPE_RAW_SAMPLE_RATE", "48000"),
                              "--channels", qEnvironmentVariable("AVSCOPE_RAW_CHANNELS", "2"),
                              "--bits-per-sample", qEnvironmentVariable("AVSCOPE_RAW_BITS", "16"),
                              "--endian", qEnvironmentVariable("AVSCOPE_RAW_ENDIAN", "little")};
        if (qEnvironmentVariableIntValue("AVSCOPE_RAW_UNSIGNED") != 0) preset << "--unsigned-pcm";
        return preset;
    }
    if (suffix == "yuv" && !qEnvironmentVariableIsEmpty("AVSCOPE_RAW_WIDTH")) {
        return {"--width", qEnvironmentVariable("AVSCOPE_RAW_WIDTH", "1920"),
                "--height", qEnvironmentVariable("AVSCOPE_RAW_HEIGHT", "1080"),
                "--pixel-format", qEnvironmentVariable("AVSCOPE_RAW_PIXEL_FORMAT", "yuv420p"),
                "--fps", qEnvironmentVariable("AVSCOPE_RAW_FPS", "25")};
    }

    QDialog dialog(this);
    dialog.setWindowTitle(suffix == "pcm" ? tr("Raw PCM 参数") : tr("Raw YUV 参数"));
    auto *layout = new QVBoxLayout(&dialog);
    auto *hint = new QLabel(suffix == "pcm"
        ? tr("裸 PCM 没有头信息，请指定采样格式。参数会保存为下次默认值。")
        : tr("裸 YUV 没有头信息，请指定画面格式。参数会保存为下次默认值。"));
    hint->setWordWrap(true);
    hint->setObjectName("sectionHint");
    layout->addWidget(hint);
    auto *form = new QFormLayout;
    layout->addLayout(form);

    QStringList result;
    if (suffix == "pcm") {
        auto *sampleRate = new QSpinBox;
        sampleRate->setRange(1000, 768000);
        sampleRate->setValue(m_settings.value("raw/pcmSampleRate", 48000).toInt());
        auto *channels = new QSpinBox;
        channels->setRange(1, 32);
        channels->setValue(m_settings.value("raw/pcmChannels", 2).toInt());
        auto *bits = new QComboBox;
        bits->addItems({"8", "16", "24", "32", "64"});
        bits->setCurrentText(m_settings.value("raw/pcmBits", "16").toString());
        auto *endian = new QComboBox;
        endian->addItems({"little", "big"});
        endian->setCurrentText(m_settings.value("raw/pcmEndian", "little").toString());
        auto *unsignedPcm = new QCheckBox(tr("无符号 PCM"));
        unsignedPcm->setChecked(m_settings.value("raw/pcmUnsigned", false).toBool());
        form->addRow(tr("采样率 (Hz)"), sampleRate);
        form->addRow(tr("声道数"), channels);
        form->addRow(tr("位深"), bits);
        form->addRow(tr("端序"), endian);
        form->addRow(QString(), unsignedPcm);
        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
        connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
        layout->addWidget(buttons);
        if (dialog.exec() != QDialog::Accepted) { *accepted = false; return {}; }
        m_settings.setValue("raw/pcmSampleRate", sampleRate->value());
        m_settings.setValue("raw/pcmChannels", channels->value());
        m_settings.setValue("raw/pcmBits", bits->currentText());
        m_settings.setValue("raw/pcmEndian", endian->currentText());
        m_settings.setValue("raw/pcmUnsigned", unsignedPcm->isChecked());
        result = {"--sample-rate", QString::number(sampleRate->value()), "--channels", QString::number(channels->value()),
                  "--bits-per-sample", bits->currentText(), "--endian", endian->currentText()};
        if (unsignedPcm->isChecked()) result << "--unsigned-pcm";
    } else {
        auto *width = new QSpinBox;
        width->setRange(1, 16384);
        width->setValue(m_settings.value("raw/yuvWidth", 1920).toInt());
        auto *height = new QSpinBox;
        height->setRange(1, 16384);
        height->setValue(m_settings.value("raw/yuvHeight", 1080).toInt());
        auto *pixelFormat = new QComboBox;
        pixelFormat->addItems({"yuv420p", "nv12", "nv21", "yuyv422"});
        pixelFormat->setCurrentText(m_settings.value("raw/yuvPixelFormat", "yuv420p").toString());
        auto *fps = new QDoubleSpinBox;
        fps->setRange(0.001, 1000.0);
        fps->setDecimals(3);
        fps->setValue(m_settings.value("raw/yuvFps", 25.0).toDouble());
        form->addRow(tr("宽度"), width);
        form->addRow(tr("高度"), height);
        form->addRow(tr("像素格式"), pixelFormat);
        form->addRow(tr("帧率"), fps);
        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
        connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
        layout->addWidget(buttons);
        if (dialog.exec() != QDialog::Accepted) { *accepted = false; return {}; }
        m_settings.setValue("raw/yuvWidth", width->value());
        m_settings.setValue("raw/yuvHeight", height->value());
        m_settings.setValue("raw/yuvPixelFormat", pixelFormat->currentText());
        m_settings.setValue("raw/yuvFps", fps->value());
        result = {"--width", QString::number(width->value()), "--height", QString::number(height->value()),
                  "--pixel-format", pixelFormat->currentText(), "--fps", QString::number(fps->value())};
    }
    return result;
}

void MainWindow::analysisFinished(int exitCode, QProcess::ExitStatus status)
{
    setAnalysisBusy(false);
    const QString task = m_taskKind;
    m_taskKind.clear();
    if (m_cancelRequested) {
        m_cancelRequested = false;
        m_statusText->setText(tr("任务已取消"));
        m_log->appendPlainText(tr("[%1] 用户取消任务").arg(QTime::currentTime().toString("HH:mm:ss")));
        return;
    }
    if (status != QProcess::NormalExit || exitCode != 0) {
        const auto error = QString::fromUtf8(m_process->readAllStandardError());
        const QString label = task == "compare" ? tr("对比") : task == "export" ? tr("导出") : tr("分析");
        m_statusText->setText(tr("%1失败").arg(label));
        m_log->appendPlainText(tr("[错误] %1").arg(error));
        QMessageBox::critical(this, tr("%1失败").arg(label), error.isEmpty() ? tr("侧车进程异常退出。") : error);
        return;
    }
    if (task == "compare") {
        QFile file(m_taskOutputPath);
        if (!file.open(QIODevice::ReadOnly)) {
            QMessageBox::critical(this, tr("读取失败"), tr("无法读取对比结果：%1").arg(m_taskOutputPath));
            return;
        }
        QJsonParseError error;
        const auto document = QJsonDocument::fromJson(file.readAll(), &error);
        if (document.isNull()) {
            QMessageBox::critical(this, tr("对比结果无效"), error.errorString());
            return;
        }
        populateCompare(m_taskMode, document, m_taskOtherPath);
        const QString legacyCompare = projectRoot() + QString("/tmp/qt-runtime/compare-%1.json").arg(m_taskMode);
        QFile::remove(legacyCompare);
        QFile::copy(m_taskOutputPath, legacyCompare);
        m_tabs->setCurrentWidget(m_taskMode == "binary" ? static_cast<QWidget *>(m_hexCompare)
                                                        : static_cast<QWidget *>(m_compareTree));
        m_statusText->setText(tr("对比完成：%1").arg(QFileInfo(m_taskOtherPath).fileName()));
        m_log->appendPlainText(tr("[%1] %2 对比完成：%3").arg(QTime::currentTime().toString("HH:mm:ss"), m_taskMode, m_taskOtherPath));
        return;
    }
    if (task == "export") {
        m_log->appendPlainText(tr("[导出] %1").arg(m_taskOutputPath));
        m_statusText->setText(tr("报告已导出：%1").arg(m_taskOutputPath));
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
    const QString legacyAnalysis = projectRoot() + "/tmp/qt-runtime/current-analysis.json";
    QFile::remove(legacyAnalysis);
    QFile::copy(analysisOutputPath(), legacyAnalysis);
    const auto completedSummary = document.object().value("media").toObject().value("summary").toObject();
    m_previewPosition = completedSummary.value("video_preview").toObject().value("position_seconds").toDouble(m_previewPosition);
    m_previewFrame = completedSummary.value("yuv_preview").toObject().value("frame_index").toInt(m_previewFrame);
    const auto info = QFileInfo(m_currentPath);
    addRecentFile(m_currentPath);
    m_statusText->setText(tr("%1  |  分析完成").arg(info.fileName()));
    m_log->appendPlainText(tr("[%1] 分析完成").arg(QTime::currentTime().toString("HH:mm:ss")));
    const QString autoMode = qEnvironmentVariable("AVSCOPE_COMPARE_MODE");
    const QString autoPath = qEnvironmentVariable("AVSCOPE_COMPARE_PATH");
    if (!m_autoCompareTriggered && !autoMode.isEmpty() && QFileInfo::exists(autoPath)) {
        m_autoCompareTriggered = true;
        QTimer::singleShot(0, this, [this, autoMode] { runCompare(autoMode); });
    }
    if (!m_autoPreviewTriggered && qEnvironmentVariableIntValue("AVSCOPE_PREVIEW_STEP") != 0) {
        m_autoPreviewTriggered = true;
        const int direction = qEnvironmentVariableIntValue("AVSCOPE_PREVIEW_STEP") > 0 ? 1 : -1;
        QTimer::singleShot(0, this, [this, direction] { stepMediaPreview(direction); });
    }
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

void MainWindow::startEngineTask(const QString &kind, const QStringList &arguments)
{
    if (m_process->state() != QProcess::NotRunning) {
        QMessageBox::information(this, tr("任务进行中"), tr("请等待当前任务结束，或先点击取消。"));
        return;
    }
    auto environment = QProcessEnvironment::systemEnvironment();
    environment.insert("PYTHONPATH", projectRoot());
#ifdef Q_OS_WIN
    // Some existing Windows worktrees retain the historical "AVScope"
    // directory casing even though the canonical Python package is "avscope".
    environment.insert("PYTHONCASEOK", "1");
#endif
    environment.insert("TEMP", projectRoot() + "/tmp");
    environment.insert("TMP", projectRoot() + "/tmp");
    m_process->setProcessEnvironment(environment);
    m_process->setWorkingDirectory(projectRoot());
    m_cancelRequested = false;
    m_taskKind = kind;
    setAnalysisBusy(true);
    m_process->start(engineExecutable(), engineArguments(arguments));
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
    QJsonArray frameRows = frames;
    if (frameRows.isEmpty()) {
        const auto packets = media.value("summary").toObject().value("packet_timeline").toObject().value("packets").toArray();
        for (const auto &value : packets) {
            const auto packet = value.toObject();
            QJsonObject row;
            row["index"] = packet.value("index");
            row["offset"] = packet.value("pos");
            row["size"] = packet.value("size");
            row["pts"] = packet.value("pts");
            row["dts"] = packet.value("dts");
            row["duration"] = packet.value("duration");
            row["frame_type"] = tr("%1 包 · 流 %2")
                .arg(packet.value("codec_type").toString("data"), displayValue(packet.value("stream_index")));
            row["keyframe"] = packet.value("keyframe");
            frameRows.append(row);
        }
    }
    populateFrames(frameRows);
    populateStreams(media, frameRows);
    populateTransportSessions(media.value("summary").toObject().value("transport_sessions").toObject());
    populateRtpVideo(media.value("summary").toObject().value("rtp_video").toObject());
    populateSipSdp(media.value("summary").toObject().value("sip_sdp").toObject());
    populateRtcpFeedback(media.value("summary").toObject().value("rtcp").toObject());
    populateRtpTiming(media.value("summary").toObject().value("transport_sessions").toObject());
    populateTwcc(media.value("summary").toObject().value("rtcp").toObject());
    populateCodecHealth(media.value("summary").toObject().value("codec_health").toObject());
    populateDiagnostics(diagnostics, media);
    m_timeline->setData(frameRows, media.value("summary").toObject().value("timeline_summary").toObject());

    m_formatMetric->setText(media.value("format_name").toString("--"));
    m_sizeMetric->setText(formatSize(jsonInteger(media.value("size"))));
    m_nodeMetric->setText(tr("%1 / %2").arg(countNodes(root)).arg(countFields(root)));
    m_issueMetric->setText(diagnostics.isEmpty() ? tr("通过") : tr("%1 项").arg(diagnostics.size()));
    m_fileLabel->setToolTip(media.value("path").toString());

    const auto summary = media.value("summary").toObject();
    m_preview->setMedia(media);
    const int requestedHexPageSize = qEnvironmentVariableIntValue("AVSCOPE_HEX_PAGE_SIZE");
    if (requestedHexPageSize > 0) {
        const int pageSizeIndex = m_hexPageSizeCombo->findData(requestedHexPageSize);
        if (pageSizeIndex >= 0) {
            QSignalBlocker blocker(m_hexPageSizeCombo);
            m_hexPageSizeCombo->setCurrentIndex(pageSizeIndex);
            m_hexPageSize = requestedHexPageSize;
        }
    }
    const int requestedHexPage = qMax(0, qEnvironmentVariableIntValue("AVSCOPE_HEX_PAGE"));
    renderHexPage(static_cast<qint64>(requestedHexPage) * m_hexPageSize,
                  requestedHexPage == 0 ? m_hexOffset : -1,
                  m_hexFocusSize);
    const auto requestedTab = qEnvironmentVariable("AVSCOPE_START_TAB");
    if (!requestedTab.isEmpty()) {
        bool ok = false;
        const int index = requestedTab.toInt(&ok);
        if (ok && index >= 0 && index < m_tabs->count())
            m_tabs->setCurrentIndex(index);
    }
    const auto requestedTransportTab = qEnvironmentVariable("AVSCOPE_TRANSPORT_DETAIL_TAB");
    if (!requestedTransportTab.isEmpty() && m_transportDetails) {
        bool ok = false;
        const int index = requestedTransportTab.toInt(&ok);
        if (ok && index >= 0 && index < m_transportDetails->count())
            m_transportDetails->setCurrentIndex(index);
    }
}

void MainWindow::populateProtocolTree(const QJsonObject &node, QTreeWidgetItem *parent)
{
    auto *item = parent ? new QTreeWidgetItem(parent) : new QTreeWidgetItem(m_protocolTree);
    const qint64 offset = jsonInteger(node.value("offset"));
    const qint64 size = jsonInteger(node.value("size"));
    const QString severity = node.value("severity").toString();
    const bool isRoot = parent == nullptr;
    const bool isContainer = !node.value("children").toArray().isEmpty();
    item->setText(0, node.value("name").toString());
    item->setText(1, node.value("node_type").toString());
    item->setText(3, QString("0x%1").arg(offset, 0, 16).toUpper());
    item->setText(4, QString::number(size));
    item->setIcon(0, protocolTreeIcon(false, isContainer, isRoot, severity, m_dark));
    item->setData(0, NodeRole, node);
    item->setData(0, OffsetRole, offset);
    item->setData(0, SizeRole, size);
    item->setToolTip(0, node.value("description").toString());
    QFont nodeFont = item->font(0);
    nodeFont.setWeight(isRoot ? QFont::DemiBold : (isContainer ? QFont::Medium : QFont::Normal));
    item->setFont(0, nodeFont);
    item->setForeground(0, QColor(m_dark ? "#DCE6EF" : "#243442"));
    item->setForeground(1, QColor(m_dark ? "#72B8D8" : "#2D7296"));
    item->setForeground(3, QColor(m_dark ? "#8EA0B0" : "#667987"));
    item->setForeground(4, QColor(m_dark ? "#8EA0B0" : "#667987"));
    if (severity == "warning" || severity == "error") {
        const QColor severityColor = severity == "error"
            ? QColor(m_dark ? "#FF7780" : "#C83E4B")
            : QColor(m_dark ? "#F2BE5C" : "#A96D0D");
        item->setForeground(0, severityColor);
    }

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
        const QString fieldSeverity = field.value("severity").toString();
        fieldItem->setIcon(0, protocolTreeIcon(true, false, false, fieldSeverity, m_dark));
        fieldItem->setData(0, NodeRole, node);
        fieldItem->setData(0, FieldRole, field);
        fieldItem->setData(0, OffsetRole, fieldOffset);
        fieldItem->setData(0, SizeRole, fieldSize);
        fieldItem->setToolTip(0, field.value("description").toString());
        const QColor valueColor = fieldColor(field.value("value"), field.value("hex_value").toString(), fieldSeverity);
        fieldItem->setForeground(0, fieldSeverity == "warning" || fieldSeverity == "error"
                                        ? valueColor : QColor(m_dark ? "#B7C5D0" : "#435867"));
        fieldItem->setForeground(1, QColor(m_dark ? "#8093A4" : "#718493"));
        fieldItem->setForeground(2, valueColor);
        fieldItem->setForeground(3, QColor(m_dark ? "#8093A4" : "#718493"));
        fieldItem->setForeground(4, QColor(m_dark ? "#8093A4" : "#718493"));
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
    m_framesSummary->setText(rows > 0
        ? tr("共 %1 个帧/包").arg(rows)
        : tr("当前文件没有可定位的帧或数据包"));
}

void MainWindow::populateStreams(const QJsonObject &media, const QJsonArray &frames)
{
    const auto summary = media.value("summary").toObject();
    QJsonArray streams = summary.value("ffprobe").toObject().value("streams").toArray();
    if (streams.isEmpty()) {
        const auto sessions = summary.value("transport_sessions").toObject().value("sessions").toArray();
        for (const auto &value : sessions) {
            const auto session = value.toObject();
            QJsonObject stream;
            stream["index"] = streams.size();
            stream["codec_type"] = session.value("video_codec").toString().isEmpty() ? "data" : "video";
            stream["codec_name"] = session.value("video_codec").toString("RTP");
            stream["profile"] = session.value("ssrc").toString();
            stream["duration"] = session.value("duration_seconds");
            stream["bit_rate"] = session.value("payload_bitrate_kbps").toDouble() > 0
                ? QString::number(session.value("payload_bitrate_kbps").toDouble(), 'f', 2) + " kbps" : QString();
            stream["format_label"] = tr("RTP · PT %1 · %2 包")
                .arg(displayValue(session.value("payload_types"))).arg(jsonInteger(session.value("packets")));
            stream["first_offset"] = session.value("first_offset");
            streams.append(stream);
        }
        if (streams.isEmpty()) {
            const QString formatName = media.value("format_name").toString();
            QString type = "data";
            QString codec = formatName;
            if (formatName.contains("H.26", Qt::CaseInsensitive) || formatName.contains("YUV", Qt::CaseInsensitive)) {
                type = "video";
            } else if (formatName.contains("AAC", Qt::CaseInsensitive) || formatName.contains("WAV", Qt::CaseInsensitive)
                       || formatName.contains("PCM", Qt::CaseInsensitive)) {
                type = "audio";
            }
            QJsonObject stream;
            stream["index"] = 0;
            stream["codec_type"] = type;
            stream["codec_name"] = codec;
            stream["profile"] = summary.value("profile").toString();
            stream["width"] = summary.value("width");
            stream["height"] = summary.value("height");
            stream["channels"] = summary.value("channels");
            stream["sample_rate"] = summary.value("sample_rate");
            stream["duration"] = summary.contains("duration_seconds") ? summary.value("duration_seconds") : summary.value("duration");
            stream["bit_rate"] = summary.contains("average_bitrate") ? summary.value("average_bitrate") : summary.value("byte_rate");
            stream["format_label"] = tr("内置解析器 · %1 项").arg(frames.size());
            stream["first_offset"] = frames.isEmpty() ? QJsonValue(0) : frames.first().toObject().value("offset");
            streams.append(stream);
        }
    }
    m_streamsTable->setRowCount(streams.size());
    for (int row = 0; row < streams.size(); ++row) {
        const auto stream = streams.at(row).toObject();
        const QString type = stream.value("codec_type").toString();
        QString shape;
        if (type == "video" && jsonInteger(stream.value("width")) > 0 && jsonInteger(stream.value("height")) > 0)
            shape = QString("%1 x %2").arg(jsonInteger(stream.value("width"))).arg(jsonInteger(stream.value("height")));
        else if (type == "audio" && jsonInteger(stream.value("channels")) > 0)
            shape = tr("%1 声道").arg(jsonInteger(stream.value("channels")));
        QString format = type == "video" ? stream.value("pix_fmt").toString() : stream.value("sample_fmt").toString();
        if (format.isEmpty()) format = stream.value("format_label").toString();
        const QStringList values = {
            displayValue(stream.value("index")), type, stream.value("codec_name").toString(), stream.value("profile").toString(),
            shape, displayValue(stream.value("sample_rate")), stream.value("avg_frame_rate").toString(),
            stream.value("time_base").toString(), displayValue(stream.value("duration")),
            displayValue(stream.value("bit_rate")), format
        };
        const QColor color = type == "video" ? QColor(m_dark ? "#6CB6FF" : "#146EA8")
                            : type == "audio" ? QColor(m_dark ? "#73D2B3" : "#17785A")
                            : QColor(m_dark ? "#C7A7FF" : "#6941C6");
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, jsonInteger(stream.value("first_offset")));
            cell->setToolTip(values.at(column));
            if (column == 1 || column == 2) cell->setForeground(color);
            m_streamsTable->setItem(row, column, cell);
        }
    }
    m_streamsTable->resizeColumnsToContents();
    m_streamsTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
}

void MainWindow::populateTransportSessions(const QJsonObject &transport)
{
    if (!m_transportSessionsTable) return;
    const auto sessions = transport.value("sessions").toArray();
    m_transportSessionsTable->setSortingEnabled(false);
    m_transportSessionsTable->setRowCount(sessions.size());
    for (int row = 0; row < sessions.size(); ++row) {
        const auto session = sessions.at(row).toObject();
        const QString status = session.value("status").toString("normal");
        const qint64 offset = jsonInteger(session.value("first_offset"));
        const auto payloadTypes = session.value("payload_types").toArray();
        QStringList ptValues;
        for (const auto &value : payloadTypes) ptValues << displayValue(value);
        const QString negotiatedEncoding = session.value("negotiated_encoding").toString();
        const qint64 negotiatedClock = jsonInteger(session.value("negotiated_clock_rate"));
        if (!negotiatedEncoding.isEmpty())
            ptValues << tr("%1 @%2").arg(negotiatedEncoding).arg(negotiatedClock);
        const QString sequenceRange = tr("%1 -> %2")
            .arg(jsonInteger(session.value("first_sequence")))
            .arg(jsonInteger(session.value("last_sequence")));
        const QString rtcp = tr("SR %1 / RB %2 / N %3 / P %4 / F %5")
            .arg(jsonInteger(session.value("rtcp_sender_reports")))
            .arg(jsonInteger(session.value("rtcp_report_blocks")))
            .arg(jsonInteger(session.value("rtcp_nack_events")))
            .arg(jsonInteger(session.value("rtcp_pli_events")))
            .arg(jsonInteger(session.value("rtcp_fir_events")));
        const double bitrate = session.value("payload_bitrate_kbps").toDouble(-1.0);
        const QStringList values = {
            status == "warning" ? tr("警告") : tr("正常"),
            session.value("endpoint").toString(), session.value("ssrc").toString(), ptValues.join(", "),
            displayValue(session.value("packets")), formatSize(jsonInteger(session.value("payload_bytes"))), sequenceRange,
            displayValue(session.value("estimated_lost_packets")), displayValue(session.value("duplicate_packets")),
            displayValue(session.value("reordered_packets")), displayValue(session.value("marker_packets")),
            bitrate < 0 ? "--" : tr("%1 kbps").arg(bitrate, 0, 'f', 3), rtcp,
            displayValue(session.value("rtcp_max_interarrival_jitter")),
            tr("%1 s").arg(session.value("rtcp_max_delay_since_last_sr_seconds").toDouble(), 0, 'f', 3)
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setData(Qt::UserRole + 10, status);
            cell->setToolTip(column == 1 ? session.value("session_id").toString() : values.at(column));
            if (status == "warning")
                cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            else if (column == 0)
                cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_transportSessionsTable->setItem(row, column, cell);
        }
        const QList<int> numericColumns = {4, 7, 8, 9, 10, 13};
        for (int column : numericColumns) {
            QJsonValue value;
            if (column == 4) value = session.value("packets");
            else if (column == 7) value = session.value("estimated_lost_packets");
            else if (column == 8) value = session.value("duplicate_packets");
            else if (column == 9) value = session.value("reordered_packets");
            else if (column == 10) value = session.value("marker_packets");
            else value = session.value("rtcp_max_interarrival_jitter");
            m_transportSessionsTable->item(row, column)->setData(Qt::EditRole, jsonInteger(value));
        }
    }
    m_transportSessionsTable->setSortingEnabled(true);
    const int count = jsonInteger(transport.value("session_count"));
    const int warnings = jsonInteger(transport.value("warning_sessions"));
    m_transportSummary->setText(
        tr("会话 %1  |  RTP %2 包  |  丢失/重复/乱序 %3/%4/%5  |  RTCP %6  |  反馈 %7  |  结束 %8  |  SDP %9")
            .arg(count)
            .arg(jsonInteger(transport.value("total_rtp_packets")))
            .arg(jsonInteger(transport.value("estimated_lost_packets")))
            .arg(jsonInteger(transport.value("duplicate_packets")))
            .arg(jsonInteger(transport.value("reordered_packets")))
            .arg(jsonInteger(transport.value("rtcp_linked_sessions")))
            .arg(jsonInteger(transport.value("rtcp_feedback_sessions")))
            .arg(jsonInteger(transport.value("rtcp_ended_sessions")))
            .arg(jsonInteger(transport.value("sdp_linked_sessions"))));
    m_transportIssuesOnly->setEnabled(warnings > 0);
    if (!qEnvironmentVariableIsEmpty("AVSCOPE_TRANSPORT_ISSUES_ONLY"))
        m_transportIssuesOnly->setChecked(qEnvironmentVariableIntValue("AVSCOPE_TRANSPORT_ISSUES_ONLY") != 0);
    else if (warnings == 0)
        m_transportIssuesOnly->setChecked(false);
    filterTransportSessions();
}

void MainWindow::filterTransportSessions()
{
    if (!m_transportSessionsTable) return;
    const bool issuesOnly = m_transportIssuesOnly && m_transportIssuesOnly->isChecked();
    for (int row = 0; row < m_transportSessionsTable->rowCount(); ++row) {
        const auto *item = m_transportSessionsTable->item(row, 0);
        const bool warning = item && item->data(Qt::UserRole + 10).toString() == "warning";
        m_transportSessionsTable->setRowHidden(row, issuesOnly && !warning);
    }
    const QString statePath = qEnvironmentVariable("AVSCOPE_TRANSPORT_STATE");
    if (!statePath.isEmpty()) {
        int visible = 0;
        for (int row = 0; row < m_transportSessionsTable->rowCount(); ++row)
            visible += !m_transportSessionsTable->isRowHidden(row);
        QJsonObject state{
            {"visible", visible},
            {"total", m_transportSessionsTable->rowCount()},
            {"issues_only", issuesOnly},
        };
        QFile file(statePath);
        QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate))
            file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateRtpVideo(const QJsonObject &video)
{
    if (!m_rtpVideoStreamsTable || !m_rtpVideoIssuesTable || !m_rtpVideoSummary) return;
    const auto streams = video.value("streams").toArray();
    const auto issues = video.value("issues").toArray();
    const auto objectText = [](const QJsonObject &object) {
        QStringList values;
        for (auto it = object.begin(); it != object.end(); ++it)
            values << QString("%1 %2").arg(it.key(), displayValue(it.value()));
        return values.isEmpty() ? QString("--") : values.join(", ");
    };
    m_rtpVideoStreamsTable->setSortingEnabled(false);
    m_rtpVideoStreamsTable->setRowCount(streams.size());
    for (int row = 0; row < streams.size(); ++row) {
        const auto stream = streams.at(row).toObject();
        const bool warning = stream.value("status").toString() == "warning";
        const qint64 offset = jsonInteger(stream.value("first_offset"));
        const QStringList values = {
            warning ? tr("警告") : tr("正常"), stream.value("codec").toString(), stream.value("ssrc").toString(),
            objectText(stream.value("packetization_counts").toObject()), objectText(stream.value("nal_type_counts").toObject()),
            tr("%1 / %2").arg(jsonInteger(stream.value("packets"))).arg(jsonInteger(stream.value("nal_units"))),
            tr("%1 / %2").arg(jsonInteger(stream.value("completed_fragments"))).arg(jsonInteger(stream.value("incomplete_fragments"))),
            displayValue(stream.value("issue_count")),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setData(Qt::UserRole + 10, stream.value("status").toString());
            cell->setToolTip(tr("%1\n首个 Payload Offset 0x%2")
                                 .arg(stream.value("endpoint").toString()).arg(offset, 0, 16).toUpper());
            if (warning) cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            else if (column == 0) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            else if (column == 1) cell->setForeground(QColor(m_dark ? "#7CC9F3" : "#176A99"));
            m_rtpVideoStreamsTable->setItem(row, column, cell);
        }
        m_rtpVideoStreamsTable->item(row, 7)->setData(Qt::EditRole, jsonInteger(stream.value("issue_count")));
    }
    m_rtpVideoStreamsTable->setSortingEnabled(true);

    m_rtpVideoIssuesTable->setRowCount(issues.size());
    for (int row = 0; row < issues.size(); ++row) {
        const auto issue = issues.at(row).toObject();
        const qint64 offset = jsonInteger(issue.value("offset"));
        const QStringList values = {tr("警告"), QString("0x%1").arg(offset, 0, 16).toUpper(), issue.value("message").toString()};
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            m_rtpVideoIssuesTable->setItem(row, column, cell);
        }
    }
    QStringList codecs;
    for (const auto &codec : video.value("codecs").toArray()) codecs << codec.toString();
    m_rtpVideoSummary->setText(
        streams.isEmpty() ? tr("当前文件没有可识别的 RTP H.264/H.265 视频负载")
                          : tr("视频流 %1  |  编码 %2  |  RTP %3 包  |  NALU %4  |  完成分片 %5  |  未完成 %6  |  问题 %7")
                                .arg(streams.size()).arg(codecs.join(" / ")).arg(jsonInteger(video.value("packets")))
                                .arg(jsonInteger(video.value("nal_units"))).arg(jsonInteger(video.value("completed_fragments")))
                                .arg(jsonInteger(video.value("incomplete_fragments"))).arg(issues.size()));

    const QString statePath = qEnvironmentVariable("AVSCOPE_RTP_VIDEO_STATE");
    if (!statePath.isEmpty()) {
        QJsonObject state{{"streams", streams.size()}, {"issues", issues.size()}, {"nal_units", video.value("nal_units")},
                          {"completed_fragments", video.value("completed_fragments")},
                          {"incomplete_fragments", video.value("incomplete_fragments")}, {"codecs", video.value("codecs")}};
        QFile file(statePath);
        QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate))
            file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateSipSdp(const QJsonObject &signaling)
{
    if (!m_sipMessagesTable || !m_sdpMappingsTable || !m_sipSdpSummary) return;
    const auto messages = signaling.value("messages").toArray();
    const auto mappings = signaling.value("unique_payload_mappings").toArray();
    m_sipMessagesTable->setRowCount(messages.size());
    for (int row = 0; row < messages.size(); ++row) {
        const auto message = messages.at(row).toObject();
        const qint64 offset = jsonInteger(message.value("offset"));
        const bool response = message.value("kind").toString() == "response";
        const int statusCode = static_cast<int>(jsonInteger(message.value("status_code")));
        const QString methodStatus = response
            ? tr("%1 %2").arg(statusCode).arg(message.value("start_line").toString().section(' ', 2))
            : message.value("method").toString();
        const QStringList values = {
            QString::number(row), response ? tr("响应") : tr("请求"), methodStatus,
            message.value("call_id").toString(), message.value("cseq").toString(),
            tr("%1 -> %2").arg(message.value("source_endpoint").toString(), message.value("destination_endpoint").toString()),
            message.value("has_sdp").toBool() ? tr("是") : tr("否"),
            QString("0x%1").arg(offset, 0, 16).toUpper(),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setToolTip(message.value("start_line").toString());
            if (statusCode >= 400) cell->setForeground(QColor(m_dark ? "#FF8A92" : "#B4232F"));
            else if (response) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            else if (column == 2) cell->setForeground(QColor(m_dark ? "#7CC9F3" : "#176A99"));
            m_sipMessagesTable->setItem(row, column, cell);
        }
    }

    m_sdpMappingsTable->setRowCount(mappings.size());
    for (int row = 0; row < mappings.size(); ++row) {
        const auto mapping = mappings.at(row).toObject();
        const qint64 offset = jsonInteger(mapping.value("offset"));
        const QString encoding = mapping.value("encoding").toString();
        const QStringList values = {
            mapping.value("call_id").toString(), mapping.value("media").toString(),
            tr("%1 : %2").arg(mapping.value("connection_address").toString()).arg(jsonInteger(mapping.value("port"))),
            displayValue(mapping.value("payload_type")), encoding, displayValue(mapping.value("clock_rate")),
            displayValue(mapping.value("channels")), mapping.value("direction").toString(), mapping.value("fmtp").toString(),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setToolTip(mapping.value("rtpmap").toString());
            if (column == 4 && (encoding == "H264" || encoding == "H265"))
                cell->setForeground(QColor(m_dark ? "#7CC9F3" : "#176A99"));
            else if (column == 4)
                cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_sdpMappingsTable->setItem(row, column, cell);
        }
    }
    m_sipSdpSummary->setText(
        messages.isEmpty() ? tr("当前文件没有 SIP/SDP 信令")
                           : tr("SIP %1 条  |  请求 %2  |  响应 %3  |  Call-ID %4  |  SDP 媒体 %5  |  PT 映射 %6")
                                 .arg(messages.size()).arg(jsonInteger(signaling.value("requests")))
                                 .arg(jsonInteger(signaling.value("responses"))).arg(jsonInteger(signaling.value("call_count")))
                                 .arg(jsonInteger(signaling.value("media_count"))).arg(mappings.size()));

    const QString statePath = qEnvironmentVariable("AVSCOPE_SIP_SDP_STATE");
    if (!statePath.isEmpty()) {
        QJsonObject state{{"messages", messages.size()}, {"calls", signaling.value("call_count")},
                          {"media", signaling.value("media_count")}, {"mappings", mappings.size()},
                          {"issues", signaling.value("issue_count")}};
        QFile file(statePath);
        QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate))
            file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateRtcpFeedback(const QJsonObject &rtcp)
{
    if (!m_rtcpFeedbackTable || !m_rtcpMetadataTable || !m_rtcpFeedbackSummary) return;
    QJsonArray feedback;
    for (const auto &value : rtcp.value("feedback_events").toArray()) {
        const auto kind = value.toObject().value("kind").toString();
        if (kind != "TWCC" && kind != "REMB") feedback.append(value);
    }
    const auto sdes = rtcp.value("sdes_chunks").toArray();
    const auto bye = rtcp.value("bye_events").toArray();
    m_rtcpFeedbackTable->setRowCount(feedback.size());
    for (int row = 0; row < feedback.size(); ++row) {
        const auto event = feedback.at(row).toObject();
        const QString kind = event.value("kind").toString();
        const qint64 offset = jsonInteger(event.value("offset"));
        QString detail;
        if (kind == "NACK") {
            QStringList sequences;
            for (const auto &value : event.value("lost_sequences").toArray()) sequences << displayValue(value);
            detail = tr("丢失序号 %1").arg(sequences.join(", "));
        } else if (kind == "FIR") {
            detail = tr("FIR sequence %1").arg(displayValue(event.value("fir_sequence")));
        } else {
            detail = tr("请求立即生成完整图像");
        }
        const QStringList values = {
            kind, QString("0x%1").arg(jsonInteger(event.value("sender_ssrc")), 8, 16, QLatin1Char('0')).toUpper(),
            QString("0x%1").arg(jsonInteger(event.value("media_ssrc")), 8, 16, QLatin1Char('0')).toUpper(), detail,
            displayValue(event.value("fmt")), QString("0x%1").arg(offset, 0, 16).toUpper(),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setToolTip(detail);
            if (column == 0) {
                if (kind == "NACK") cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
                else if (kind == "PLI") cell->setForeground(QColor(m_dark ? "#FF8A92" : "#B4232F"));
                else cell->setForeground(QColor(m_dark ? "#C4A7F5" : "#6941A5"));
            } else if (column == 2) {
                cell->setForeground(QColor(m_dark ? "#7CC9F3" : "#176A99"));
            }
            m_rtcpFeedbackTable->setItem(row, column, cell);
        }
    }

    m_rtcpMetadataTable->setRowCount(sdes.size() + bye.size());
    int row = 0;
    for (const auto &value : sdes) {
        const auto item = value.toObject();
        const qint64 offset = jsonInteger(item.value("offset"));
        const QStringList values = {"SDES", QString("0x%1").arg(jsonInteger(item.value("ssrc")), 8, 16, QLatin1Char('0')).toUpper(),
                                    item.value("cname").toString("--"), QString("0x%1").arg(offset, 0, 16).toUpper()};
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column)); cell->setData(OffsetRole, offset);
            if (column == 0) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_rtcpMetadataTable->setItem(row, column, cell);
        }
        ++row;
    }
    for (const auto &value : bye) {
        const auto item = value.toObject();
        const qint64 offset = jsonInteger(item.value("offset"));
        QStringList ssrcs;
        for (const auto &ssrc : item.value("ssrcs").toArray())
            ssrcs << QString("0x%1").arg(jsonInteger(ssrc), 8, 16, QLatin1Char('0')).toUpper();
        const QStringList values = {"BYE", ssrcs.join(", "), item.value("reason").toString("--"),
                                    QString("0x%1").arg(offset, 0, 16).toUpper()};
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column)); cell->setData(OffsetRole, offset);
            if (column == 0) cell->setForeground(QColor(m_dark ? "#94A3B2" : "#536574"));
            m_rtcpMetadataTable->setItem(row, column, cell);
        }
        ++row;
    }
    m_rtcpFeedbackSummary->setText(
        feedback.isEmpty() && sdes.isEmpty() && bye.isEmpty() ? tr("当前文件没有 RTCP 控制反馈")
        : tr("NACK %1  |  丢失序号 %2  |  PLI %3  |  FIR %4  |  SDES %5  |  BYE %6")
              .arg(jsonInteger(rtcp.value("nack_events"))).arg(jsonInteger(rtcp.value("nack_lost_sequences")))
              .arg(jsonInteger(rtcp.value("pli_events"))).arg(jsonInteger(rtcp.value("fir_events")))
              .arg(sdes.size()).arg(bye.size()));

    const QString statePath = qEnvironmentVariable("AVSCOPE_RTCP_FEEDBACK_STATE");
    if (!statePath.isEmpty()) {
        QJsonObject state{{"feedback", feedback.size()}, {"nack", rtcp.value("nack_events")},
                          {"lost_sequences", rtcp.value("nack_lost_sequences")}, {"pli", rtcp.value("pli_events")},
                          {"fir", rtcp.value("fir_events")}, {"sdes", sdes.size()}, {"bye", bye.size()}};
        QFile file(statePath); QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate))
            file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateRtpTiming(const QJsonObject &transport)
{
    if (!m_rtpTimingTable || !m_rtpTimingEventsTable || !m_rtpTimingSummary) return;
    const auto sessions = transport.value("sessions").toArray();
    const auto summary = transport.value("rtp_timing").toObject();
    m_rtpTimingTable->setSortingEnabled(false);
    m_rtpTimingTable->setRowCount(sessions.size());
    int eventCount = 0;
    for (const auto &value : sessions) eventCount += value.toObject().value("rtp_timing").toObject().value("events").toArray().size();
    m_rtpTimingEventsTable->setRowCount(eventCount);
    int eventRow = 0;
    for (int row = 0; row < sessions.size(); ++row) {
        const auto session = sessions.at(row).toObject();
        const auto timing = session.value("rtp_timing").toObject();
        const qint64 offset = jsonInteger(session.value("first_offset"));
        const bool available = timing.value("available").toBool();
        const bool warning = timing.value("status").toString() == "warning";
        const QString status = !available ? tr("不可计算") : warning ? tr("警告") : tr("正常");
        const QString clock = jsonInteger(timing.value("clock_rate")) > 0
            ? tr("%1 Hz / %2").arg(jsonInteger(timing.value("clock_rate"))).arg(timing.value("clock_source").toString()) : "--";
        const QStringList values = {
            status, session.value("endpoint").toString(), session.value("ssrc").toString(), clock,
            displayValue(timing.value("packet_count")), available ? tr("%1 ms").arg(timing.value("rfc3550_jitter_ms").toDouble(), 0, 'f', 3) : "--",
            available ? tr("%1 ms").arg(timing.value("average_arrival_interval_ms").toDouble(), 0, 'f', 3) : "--",
            available ? tr("%1 - %2 ms").arg(timing.value("min_arrival_interval_ms").toDouble(), 0, 'f', 3)
                                              .arg(timing.value("max_arrival_interval_ms").toDouble(), 0, 'f', 3) : "--",
            available ? tr("%1 ms").arg(timing.value("max_abs_deviation_ms").toDouble(), 0, 'f', 3) : "--",
            displayValue(timing.value("burst_events")),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column)); cell->setData(OffsetRole, offset);
            if (warning) cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            else if (available && column == 0) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            else if (!available && column == 0) cell->setForeground(QColor(m_dark ? "#94A3B2" : "#536574"));
            else if (column == 5) cell->setForeground(QColor(m_dark ? "#7CC9F3" : "#176A99"));
            m_rtpTimingTable->setItem(row, column, cell);
        }
        for (const auto &eventValue : timing.value("events").toArray()) {
            const auto event = eventValue.toObject();
            const qint64 eventOffset = jsonInteger(event.value("offset"));
            const QStringList eventValues = {
                session.value("ssrc").toString(), displayValue(event.value("sequence")),
                tr("%1 ms").arg(event.value("arrival_interval_ms").toDouble(), 0, 'f', 3),
                tr("%1 ms").arg(event.value("media_interval_ms").toDouble(), 0, 'f', 3),
                tr("%1 ms").arg(event.value("deviation_ms").toDouble(), 0, 'f', 3),
                tr("%1 ms").arg(timing.value("burst_threshold_ms").toDouble(), 0, 'f', 1),
                QString("0x%1").arg(eventOffset, 0, 16).toUpper(),
            };
            for (int column = 0; column < eventValues.size(); ++column) {
                auto *cell = new QTableWidgetItem(eventValues.at(column)); cell->setData(OffsetRole, eventOffset);
                cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
                m_rtpTimingEventsTable->setItem(eventRow, column, cell);
            }
            ++eventRow;
        }
    }
    m_rtpTimingTable->setSortingEnabled(true);
    m_rtpTimingSummary->setText(
        !summary.value("available").toBool() ? tr("当前文件没有可计算的 RTP 时序质量")
        : tr("可计算会话 %1  |  警告 %2  |  最大 Jitter %3 ms  |  最大偏差 %4 ms  |  突发 %5")
              .arg(jsonInteger(summary.value("session_count"))).arg(jsonInteger(summary.value("warning_sessions")))
              .arg(summary.value("max_rfc3550_jitter_ms").toDouble(), 0, 'f', 3)
              .arg(summary.value("max_abs_deviation_ms").toDouble(), 0, 'f', 3)
              .arg(jsonInteger(summary.value("burst_events"))));
    const QString statePath = qEnvironmentVariable("AVSCOPE_RTP_TIMING_STATE");
    if (!statePath.isEmpty()) {
        QJsonObject state{{"sessions", summary.value("session_count")}, {"warnings", summary.value("warning_sessions")},
                          {"max_jitter_ms", summary.value("max_rfc3550_jitter_ms")},
                          {"max_deviation_ms", summary.value("max_abs_deviation_ms")}, {"bursts", summary.value("burst_events")}};
        QFile file(statePath); QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateTwcc(const QJsonObject &rtcp)
{
    if (!m_twccFeedbackTable || !m_twccPacketsTable || !m_rembTable || !m_twccSummary) return;
    const auto events = rtcp.value("twcc_events").toArray();
    const auto rembEvents = rtcp.value("remb_events").toArray();
    m_twccFeedbackTable->setRowCount(events.size());
    int packetCount = 0;
    for (const auto &value : events) packetCount += value.toObject().value("packets").toArray().size();
    m_twccPacketsTable->setRowCount(packetCount);
    m_rembTable->setRowCount(rembEvents.size());
    int packetRow = 0;
    for (int row = 0; row < events.size(); ++row) {
        const auto event = events.at(row).toObject();
        const qint64 offset = jsonInteger(event.value("offset"));
        const bool warning = jsonInteger(event.value("lost_packets")) > 0 || event.value("max_abs_delta_ms").toDouble() > 20.0;
        const QStringList values = {
            QString("0x%1").arg(jsonInteger(event.value("media_ssrc")), 8, 16, QLatin1Char('0')).toUpper(),
            displayValue(event.value("base_sequence")), displayValue(event.value("packet_status_count")),
            displayValue(event.value("received_packets")), displayValue(event.value("lost_packets")),
            tr("%1 ms").arg(event.value("reference_time_ms").toDouble(), 0, 'f', 0),
            displayValue(event.value("feedback_packet_count")),
            tr("%1 ms").arg(event.value("max_abs_delta_ms").toDouble(), 0, 'f', 3),
            QString("0x%1").arg(offset, 0, 16).toUpper(),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column)); cell->setData(OffsetRole, offset);
            if (warning) cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            else if (column == 3) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_twccFeedbackTable->setItem(row, column, cell);
        }
        for (const auto &packetValue : event.value("packets").toArray()) {
            const auto packet = packetValue.toObject();
            const qint64 packetOffset = jsonInteger(packet.value("offset"));
            const QString status = packet.value("status").toString();
            const bool received = packet.value("received").toBool();
            const QString statusText = status == "not_received" ? tr("未接收")
                : status == "small_delta" ? tr("Small Delta") : status == "large_delta" ? tr("Large Delta") : tr("保留");
            const QStringList packetValues = {
                displayValue(packet.value("sequence")), statusText, received ? tr("是") : tr("否"),
                packet.value("delta_ms").isNull() ? "--" : tr("%1 ms").arg(packet.value("delta_ms").toDouble(), 0, 'f', 3),
                packet.value("receive_time_ms").isNull() ? "--" : tr("%1 ms").arg(packet.value("receive_time_ms").toDouble(), 0, 'f', 3),
                displayValue(packet.value("delta_size")), QString("0x%1").arg(packetOffset, 0, 16).toUpper(),
            };
            for (int column = 0; column < packetValues.size(); ++column) {
                auto *cell = new QTableWidgetItem(packetValues.at(column)); cell->setData(OffsetRole, packetOffset);
                if (!received) cell->setForeground(QColor(m_dark ? "#FF8A92" : "#B4232F"));
                else if (status == "large_delta") cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
                else if (column == 1) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
                m_twccPacketsTable->setItem(packetRow, column, cell);
            }
            ++packetRow;
        }
    }
    for (int row = 0; row < rembEvents.size(); ++row) {
        const auto event = rembEvents.at(row).toObject();
        const qint64 offset = jsonInteger(event.value("offset"));
        QStringList targets;
        for (const auto &value : event.value("target_ssrcs").toArray())
            targets << QString("0x%1").arg(jsonInteger(value), 8, 16, QLatin1Char('0')).toUpper();
        const QStringList values = {
            QString("0x%1").arg(jsonInteger(event.value("sender_ssrc")), 8, 16, QLatin1Char('0')).toUpper(),
            targets.join(", "), tr("%1 Mbps").arg(event.value("bitrate_mbps").toDouble(), 0, 'f', 3),
            displayValue(event.value("bitrate_exponent")), displayValue(event.value("bitrate_mantissa")),
            displayValue(event.value("ssrc_count")),
            QString("0x%1").arg(jsonInteger(event.value("media_ssrc")), 8, 16, QLatin1Char('0')).toUpper(),
            QString("0x%1").arg(offset, 0, 16).toUpper(),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column)); cell->setData(OffsetRole, offset);
            if (column == 2) cell->setForeground(QColor(m_dark ? "#7CC9F3" : "#176A99"));
            else if (column == 1) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_rembTable->setItem(row, column, cell);
        }
    }
    m_twccSummary->setText(
        events.isEmpty() && rembEvents.isEmpty() ? tr("当前文件没有 TWCC / REMB 拥塞反馈")
        : tr("TWCC %1  |  收到 %2  |  丢失 %3  |  最大 Delta %4 ms  |  REMB %5  |  最低带宽 %6 Mbps")
              .arg(events.size()).arg(jsonInteger(rtcp.value("twcc_received_packets")))
              .arg(jsonInteger(rtcp.value("twcc_lost_packets")))
              .arg(rtcp.value("twcc_max_abs_delta_ms").toDouble(), 0, 'f', 3)
              .arg(rembEvents.size()).arg(jsonInteger(rtcp.value("remb_min_bitrate_bps")) / 1'000'000.0, 0, 'f', 3));
    const QString statePath = qEnvironmentVariable("AVSCOPE_TWCC_STATE");
    if (!statePath.isEmpty()) {
        QJsonObject state{{"events", events.size()}, {"received", rtcp.value("twcc_received_packets")},
                          {"lost", rtcp.value("twcc_lost_packets")}, {"max_delta_ms", rtcp.value("twcc_max_abs_delta_ms")},
                          {"packets", packetCount}, {"remb", rembEvents.size()},
                          {"remb_min_bps", rtcp.value("remb_min_bitrate_bps")}};
        QFile file(statePath); QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateCodecHealth(const QJsonObject &health)
{
    if (!m_codecIssuesTable || !m_codecParametersTable || !m_codecResolutionsTable) return;
    const bool available = health.value("available").toBool(false);
    const auto parameterSets = health.value("parameter_sets").toObject();
    const auto issues = health.value("issues").toArray();
    const auto resolutionEvents = health.value("resolution_events").toArray();
    const auto resolutionChanges = health.value("resolution_changes").toArray();
    const auto idText = [](const QJsonArray &values) {
        QStringList ids;
        for (const auto &value : values) ids << displayValue(value);
        return ids.isEmpty() ? QString("--") : ids.join(", ");
    };

    if (!available) {
        m_codecMetric->setText(tr("不适用"));
        m_codecStatusMetric->setText("--");
        m_codecParameterMetric->setText("--");
        m_codecSliceMetric->setText("--");
        m_codecIssueMetric->setText("0");
        m_codecResolutionMetric->setText("0");
    } else {
        const int vpsCount = static_cast<int>(jsonInteger(parameterSets.value("vps_count")));
        const int spsCount = static_cast<int>(jsonInteger(parameterSets.value("sps_count")));
        const int ppsCount = static_cast<int>(jsonInteger(parameterSets.value("pps_count")));
        m_codecMetric->setText(health.value("codec").toString("--"));
        m_codecStatusMetric->setText(health.value("status").toString() == "warning" ? tr("需要检查") : tr("正常"));
        m_codecParameterMetric->setText(vpsCount > 0
            ? tr("VPS %1 / SPS %2 / PPS %3").arg(vpsCount).arg(spsCount).arg(ppsCount)
            : tr("SPS %1 / PPS %2").arg(spsCount).arg(ppsCount));
        m_codecSliceMetric->setText(tr("%1 / %2").arg(jsonInteger(health.value("slices"))).arg(jsonInteger(health.value("keyframes"))));
        m_codecIssueMetric->setText(QString::number(issues.size()));
        m_codecResolutionMetric->setText(QString::number(resolutionChanges.size()));
    }

    m_codecIssuesTable->setRowCount(issues.size());
    for (int row = 0; row < issues.size(); ++row) {
        const auto issue = issues.at(row).toObject();
        const qint64 offset = jsonInteger(issue.value("offset"));
        const QStringList values = {
            issue.value("severity").toString() == "warning" ? tr("警告") : issue.value("severity").toString(),
            QString("0x%1").arg(offset, 0, 16).toUpper(),
            issue.value("message").toString(),
            issue.value("source").toString(),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            m_codecIssuesTable->setItem(row, column, cell);
        }
    }

    struct ParameterRow { QString name; QJsonArray ids; QJsonArray missing; };
    const QList<ParameterRow> parameterRows = {
        {"VPS", parameterSets.value("vps_ids").toArray(), health.value("missing_vps_ids").toArray()},
        {"SPS", parameterSets.value("sps_ids").toArray(), health.value("missing_sps_ids").toArray()},
        {"PPS", parameterSets.value("pps_ids").toArray(), health.value("missing_pps_ids").toArray()},
        {tr("Slice -> PPS"), health.value("slice_pps_ids").toArray(), health.value("missing_pps_ids").toArray()},
    };
    int parameterRowCount = 0;
    for (const auto &row : parameterRows)
        parameterRowCount += !row.ids.isEmpty() || !row.missing.isEmpty();
    m_codecParametersTable->setRowCount(parameterRowCount);
    int tableRow = 0;
    for (const auto &row : parameterRows) {
        if (row.ids.isEmpty() && row.missing.isEmpty()) continue;
        const bool warning = !row.missing.isEmpty();
        const QStringList values = {row.name, QString::number(row.ids.size()), idText(row.ids), idText(row.missing), warning ? tr("缺失引用") : tr("完整")};
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            if (warning) cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            else if (column == 4) cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_codecParametersTable->setItem(tableRow, column, cell);
        }
        ++tableRow;
    }

    QSet<qint64> changeOffsets;
    for (const auto &value : resolutionChanges)
        changeOffsets.insert(jsonInteger(value.toObject().value("offset")));
    m_codecResolutionsTable->setRowCount(resolutionEvents.size());
    for (int row = 0; row < resolutionEvents.size(); ++row) {
        const auto event = resolutionEvents.at(row).toObject();
        const qint64 offset = jsonInteger(event.value("offset"));
        const bool changed = changeOffsets.contains(offset);
        const QStringList values = {
            displayValue(event.value("parameter_set_id")), displayValue(event.value("width")),
            displayValue(event.value("height")), QString("0x%1").arg(offset, 0, 16).toUpper(),
            changed ? tr("分辨率变化") : tr("参数集出现"),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            if (changed) cell->setForeground(QColor(m_dark ? "#F5C76B" : "#8A5A00"));
            m_codecResolutionsTable->setItem(row, column, cell);
        }
    }

    const QString statePath = qEnvironmentVariable("AVSCOPE_CODEC_HEALTH_STATE");
    if (!statePath.isEmpty()) {
        QJsonObject state{
            {"available", available}, {"codec", health.value("codec")}, {"status", health.value("status")},
            {"issues", issues.size()}, {"parameter_rows", parameterRowCount},
            {"resolution_events", resolutionEvents.size()}, {"resolution_changes", resolutionChanges.size()},
        };
        QFile file(statePath);
        QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate))
            file.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

void MainWindow::populateBookmarks()
{
    if (!m_bookmarksTable) return;
    m_bookmarksTable->setRowCount(m_bookmarks.size());
    for (int row = 0; row < m_bookmarks.size(); ++row) {
        const auto bookmark = m_bookmarks.at(row).toObject();
        const qint64 offset = jsonInteger(bookmark.value("offset"));
        const QStringList values = {
            QString("0x%1").arg(offset, 0, 16).toUpper(),
            bookmark.value("note").toString(), bookmark.value("location").toString()
        };
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setData(OffsetRole, offset);
            cell->setToolTip(values.at(column));
            m_bookmarksTable->setItem(row, column, cell);
        }
    }
}

void MainWindow::onFrameSelectionChanged()
{
    const auto selected = m_framesTable->selectedItems();
    if (selected.isEmpty())
        return;
    const auto *item = selected.constFirst();
    const qint64 offset = item->data(OffsetRole).toLongLong();
    const qint64 size = item->data(SizeRole).toLongLong();
    syncProtocolTreeToRange(offset, size);
    showHex(offset, size);
    m_statusText->setText(tr("帧 #%1  |  Offset 0x%2  |  %3 bytes")
                              .arg(m_framesTable->item(item->row(), 0)->text())
                              .arg(item->data(OffsetRole).toLongLong(), 0, 16)
                              .arg(item->data(SizeRole).toLongLong()));
}

void MainWindow::syncProtocolTreeToRange(qint64 offset, qint64 size)
{
    if (!m_protocolTree || offset < 0)
        return;

    QTreeWidgetItem *bestItem = nullptr;
    QTreeWidgetItem *nearestItem = nullptr;
    qint64 bestSize = std::numeric_limits<qint64>::max();
    qint64 nearestDistance = std::numeric_limits<qint64>::max();
    bool bestContainsRange = false;
    QTreeWidgetItemIterator iterator(m_protocolTree);
    while (*iterator) {
        auto *candidate = *iterator;
        const qint64 candidateOffset = candidate->data(0, OffsetRole).toLongLong();
        const qint64 candidateSize = candidate->data(0, SizeRole).toLongLong();
        const qint64 checkedSize = qMax<qint64>(1, size);
        const bool containsStart = candidateSize > 0 && candidateOffset <= offset
            && offset - candidateOffset < candidateSize;
        const bool containsRange = containsStart && checkedSize <= candidateSize - (offset - candidateOffset);
        if (containsStart && (containsRange != bestContainsRange
                ? containsRange
                : candidateSize < bestSize)) {
            bestItem = candidate;
            bestSize = candidateSize;
            bestContainsRange = containsRange;
        }
        if (candidate->data(0, FieldRole).toJsonObject().isEmpty()
            && candidateOffset <= offset && offset - candidateOffset < nearestDistance) {
            nearestItem = candidate;
            nearestDistance = offset - candidateOffset;
        }
        ++iterator;
    }
    if (!bestItem)
        bestItem = nearestItem;
    if (!bestItem)
        return;

    bestItem->setHidden(false);
    for (auto *parent = bestItem->parent(); parent; parent = parent->parent()) {
        parent->setHidden(false);
        parent->setExpanded(true);
    }
    {
        const QSignalBlocker blocker(m_protocolTree);
        m_protocolTree->clearSelection();
        m_protocolTree->setCurrentItem(bestItem);
        bestItem->setSelected(true);
    }
    m_protocolTree->scrollToItem(bestItem, QAbstractItemView::PositionAtCenter);

    const QJsonObject node = bestItem->data(0, NodeRole).toJsonObject();
    const QJsonObject field = bestItem->data(0, FieldRole).toJsonObject();
    populateFields(node);
    showSelectionDetails(node, field);
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
    }
    m_selectionDetails->setPlainText(lines.join('\n'));
}

void MainWindow::populateDiagnostics(const QJsonArray &diagnostics, const QJsonObject &media)
{
    m_diagnostics = diagnostics;
    QSignalBlocker severityBlocker(m_diagnosticSeverityFilter);
    QSignalBlocker sourceBlocker(m_diagnosticSourceFilter);
    const QString previousSource = m_diagnosticSourceFilter->currentData().toString();
    m_diagnosticSourceFilter->clear();
    m_diagnosticSourceFilter->addItem(tr("全部来源"), "all");
    QSet<QString> sources;
    for (const auto &value : diagnostics) sources.insert(value.toObject().value("source").toString());
    QStringList sortedSources = sources.values();
    sortedSources.sort(Qt::CaseInsensitive);
    for (const auto &source : sortedSources) {
        if (!source.isEmpty()) m_diagnosticSourceFilter->addItem(source, source);
    }
    const QString configuredSource = qEnvironmentVariable("AVSCOPE_DIAGNOSTIC_SOURCE");
    const QString sourceSelection = configuredSource.isEmpty()
        ? (previousSource.isEmpty() ? m_settings.value("diagnostics/source", "all").toString() : previousSource)
        : configuredSource;
    const int sourceIndex = m_diagnosticSourceFilter->findData(sourceSelection);
    m_diagnosticSourceFilter->setCurrentIndex(sourceIndex >= 0 ? sourceIndex : 0);
    const QString severity = qEnvironmentVariable("AVSCOPE_DIAGNOSTIC_SEVERITY",
        m_settings.value("diagnostics/severity", "all").toString());
    const int severityIndex = m_diagnosticSeverityFilter->findData(severity);
    m_diagnosticSeverityFilter->setCurrentIndex(severityIndex >= 0 ? severityIndex : 0);
    m_diagnosticOffsetOnly->setChecked(qEnvironmentVariableIntValue("AVSCOPE_DIAGNOSTIC_OFFSET_ONLY") != 0
        || m_settings.value("diagnostics/offsetOnly", false).toBool());
    filterDiagnostics(media.value("format_name").toString());
}

void MainWindow::filterDiagnostics()
{
    filterDiagnostics(QString());
}

void MainWindow::filterDiagnostics(const QString &formatName)
{
    const QString severity = m_diagnosticSeverityFilter->currentData().toString();
    const QString source = m_diagnosticSourceFilter->currentData().toString();
    const bool offsetOnly = m_diagnosticOffsetOnly->isChecked();
    const bool automated = !qEnvironmentVariableIsEmpty("AVSCOPE_DIAGNOSTIC_SEVERITY")
        || !qEnvironmentVariableIsEmpty("AVSCOPE_DIAGNOSTIC_SOURCE")
        || !qEnvironmentVariableIsEmpty("AVSCOPE_DIAGNOSTIC_OFFSET_ONLY");
    if (!automated) {
        m_settings.setValue("diagnostics/severity", severity);
        m_settings.setValue("diagnostics/source", source);
        m_settings.setValue("diagnostics/offsetOnly", offsetOnly);
    }

    m_diagnosticsTable->setRowCount(0);
    int visible = 0;
    for (const auto &value : m_diagnostics) {
        const auto issue = value.toObject();
        const QString issueSeverity = issue.value("severity").toString();
        const QString issueSource = issue.value("source").toString();
        const bool hasOffset = !issue.value("offset").isNull();
        if (severity != "all" && issueSeverity != severity) continue;
        if (source != "all" && issueSource != source) continue;
        if (offsetOnly && !hasOffset) continue;
        m_diagnosticsTable->insertRow(visible);
        const qint64 offset = hasOffset ? jsonInteger(issue.value("offset")) : -1;
        const QStringList values = {
            issueSeverity.toUpper(), issueSource,
            hasOffset ? QString("0x%1").arg(offset, 0, 16).toUpper() : QString(), issue.value("message").toString()
        };
        const QColor color = issueSeverity == "error" ? QColor(m_dark ? "#FF7B81" : "#B42318")
                                                   : QColor(m_dark ? "#F5C567" : "#8A5A00");
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setForeground(color);
            cell->setToolTip(issue.value("message").toString());
            cell->setData(OffsetRole, offset);
            m_diagnosticsTable->setItem(visible, column, cell);
        }
        ++visible;
    }
    if (m_diagnostics.isEmpty() && visible == 0) {
        m_diagnosticsTable->setRowCount(1);
        const QStringList values = {tr("通过"), formatName, QString(), tr("未发现 warning / error")};
        for (int column = 0; column < values.size(); ++column) {
            auto *cell = new QTableWidgetItem(values.at(column));
            cell->setForeground(QColor(m_dark ? "#73D2B3" : "#17785A"));
            m_diagnosticsTable->setItem(0, column, cell);
        }
    }
    m_diagnosticSummary->setText(tr("显示 %1 / %2").arg(visible).arg(m_diagnostics.size()));
    const QString statePath = qEnvironmentVariable("AVSCOPE_DIAGNOSTIC_STATE");
    if (!statePath.isEmpty()) {
        QFile stateFile(statePath);
        QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (stateFile.open(QIODevice::WriteOnly)) {
            const QJsonObject state{{"visible", visible}, {"total", m_diagnostics.size()}, {"severity", severity},
                                    {"source", source}, {"offset_only", offsetOnly}};
            stateFile.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
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
    m_tabs->setCurrentWidget(m_hexPanel);
    m_statusText->setText(tr("诊断定位到 Offset 0x%1").arg(offset, 0, 16).toUpper());
}

void MainWindow::showHex(qint64 offset, qint64 size)
{
    const qint64 fileSize = QFileInfo(m_currentPath).size();
    if (fileSize <= 0) {
        m_hexView->clear();
        updateHexNavigation();
        return;
    }
    m_hexOffset = qBound<qint64>(0, offset, fileSize - 1);
    m_hexFocusSize = qMax<qint64>(1, size);
    const qint64 pageStart = (m_hexOffset / m_hexPageSize) * m_hexPageSize;
    renderHexPage(pageStart, m_hexOffset, m_hexFocusSize);
}

void MainWindow::renderHexPage(qint64 pageStart, qint64 focusOffset, qint64 focusSize)
{
    QFile file(m_currentPath);
    if (!file.open(QIODevice::ReadOnly)) {
        m_hexView->clear();
        updateHexNavigation();
        return;
    }
    const qint64 fileSize = file.size();
    if (fileSize <= 0) {
        m_hexView->clear();
        updateHexNavigation();
        return;
    }
    const qint64 lastPageStart = ((fileSize - 1) / m_hexPageSize) * m_hexPageSize;
    m_hexPageStart = qBound<qint64>(0, (pageStart / m_hexPageSize) * m_hexPageSize, lastPageStart);
    file.seek(m_hexPageStart);
    const QByteArray data = file.read(m_hexPageSize);
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
        const QString address = QString("%1").arg(m_hexPageStart + lineOffset, 12, 16, QLatin1Char('0')).toUpper();
        lines << QString("%1  %2  |%3|").arg(address, hex.join(' ').leftJustified(47, ' '), ascii);
    }
    m_hexView->clearColumnSelection();
    m_hexView->setPlainText(lines.join('\n'));
    if (focusOffset >= m_hexPageStart && focusOffset < m_hexPageStart + data.size()) {
        m_hexOffset = focusOffset;
        m_hexFocusSize = qMax<qint64>(1, focusSize);
        const int line = qBound(0, static_cast<int>((focusOffset - m_hexPageStart) / 16), qMax(0, lines.size() - 1));
        QTextCursor cursor(m_hexView->document()->findBlockByLineNumber(line));
        cursor.setPosition(cursor.block().position() + 14
                           + static_cast<int>((focusOffset - m_hexPageStart) % 16) * 3);
        m_hexView->setTextCursor(cursor);
        m_hexView->centerCursor();

        QList<QTextEdit::ExtraSelection> selections;
        const qint64 focusEnd = focusOffset
            + qMin(m_hexFocusSize, m_hexPageStart + data.size() - focusOffset);
        for (qint64 selectedOffset = focusOffset; selectedOffset < focusEnd;) {
            const int selectedLine = static_cast<int>((selectedOffset - m_hexPageStart) / 16);
            const int byteInLine = static_cast<int>((selectedOffset - m_hexPageStart) % 16);
            const int byteCount = static_cast<int>(qMin<qint64>(16 - byteInLine, focusEnd - selectedOffset));
            QTextEdit::ExtraSelection selection;
            selection.cursor = QTextCursor(m_hexView->document()->findBlockByLineNumber(selectedLine));
            if (m_hexFullLineSelection) {
                selection.cursor.select(QTextCursor::LineUnderCursor);
            } else {
                const int start = selection.cursor.block().position() + 14 + byteInLine * 3;
                selection.cursor.setPosition(start);
                selection.cursor.setPosition(start + byteCount * 3 - 1, QTextCursor::KeepAnchor);
            }
            selection.format.setBackground(m_hexView->palette().highlight());
            selection.format.setForeground(m_hexView->palette().highlightedText());
            selections.append(selection);
            selectedOffset += byteCount;
        }
        m_hexView->setExtraSelections(selections);
        m_hexView->setToolTip(tr("高亮范围：0x%1，%2 bytes；Ctrl+Shift+L 切换字节/整行高亮")
                                  .arg(focusOffset, 0, 16).arg(m_hexFocusSize));
    } else {
        m_hexOffset = m_hexPageStart;
        m_hexView->moveCursor(QTextCursor::Start);
        m_hexView->setToolTip(tr("当前页从 Offset 0x%1 开始").arg(m_hexPageStart, 0, 16).toUpper());
    }
    updateHexNavigation();
}

void MainWindow::updateHexNavigation()
{
    const qint64 fileSize = QFileInfo(m_currentPath).size();
    const qint64 end = fileSize > 0 ? qMin(fileSize, m_hexPageStart + m_hexPageSize) : 0;
    m_hexPreviousPage->setEnabled(fileSize > 0 && m_hexPageStart > 0);
    m_hexNextPage->setEnabled(fileSize > 0 && end < fileSize);
    m_hexOffsetEdit->setEnabled(fileSize > 0);
    m_hexPageSizeCombo->setEnabled(fileSize > 0);
    m_hexOffsetEdit->setText(fileSize > 0 ? QString("0x%1").arg(m_hexOffset, 0, 16).toUpper() : QString());
    m_hexRangeLabel->setText(fileSize > 0
        ? tr("可见 0x%1 - 0x%2  ·  文件 %3  ·  第 %4 / %5 页")
              .arg(m_hexPageStart, 0, 16)
              .arg(qMax<qint64>(m_hexPageStart, end - 1), 0, 16)
              .arg(formatSize(fileSize))
              .arg(m_hexPageStart / m_hexPageSize + 1)
              .arg((fileSize + m_hexPageSize - 1) / m_hexPageSize)
              .toUpper()
        : tr("尚未打开可读取的文件"));
    const QString statePath = qEnvironmentVariable("AVSCOPE_HEX_STATE");
    if (!statePath.isEmpty() && fileSize > 0) {
        QJsonObject state;
        state["path"] = QDir::toNativeSeparators(m_currentPath);
        state["file_size"] = static_cast<double>(fileSize);
        state["page_size"] = static_cast<double>(m_hexPageSize);
        state["page_index"] = static_cast<double>(m_hexPageStart / m_hexPageSize);
        state["page_count"] = static_cast<double>((fileSize + m_hexPageSize - 1) / m_hexPageSize);
        state["start_offset"] = static_cast<double>(m_hexPageStart);
        state["end_offset"] = static_cast<double>(qMax<qint64>(m_hexPageStart, end - 1));
        state["previous_enabled"] = m_hexPreviousPage->isEnabled();
        state["next_enabled"] = m_hexNextPage->isEnabled();
        QFile stateFile(statePath);
        QDir().mkpath(QFileInfo(statePath).absolutePath());
        if (stateFile.open(QIODevice::WriteOnly | QIODevice::Truncate))
            stateFile.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
    }
}

qint64 MainWindow::currentOffset() const
{
    return m_hexOffset;
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
    if (m_selectionDetails->hasFocus() && m_selectionDetails->textCursor().hasSelection()) {
        QApplication::clipboard()->setText(m_selectionDetails->textCursor().selectedText());
        m_statusText->setText(tr("已复制说明选区"));
        return;
    }
    if (m_hexView->hasFocus()) {
        const QString hexSelection = !m_hexView->columnSelectionText().isEmpty()
            ? m_hexView->columnSelectionText()
            : m_hexView->textCursor().selectedText();
        if (!hexSelection.isEmpty()) {
            QApplication::clipboard()->setText(hexSelection);
            m_statusText->setText(tr("已复制 Hex 选区"));
            return;
        }
    }
    if (m_fieldsTable->hasFocus() && m_fieldsTable->currentRow() >= 0) {
        if (auto *valueItem = m_fieldsTable->item(m_fieldsTable->currentRow(), 1)) {
            QApplication::clipboard()->setText(valueItem->text());
            m_statusText->setText(tr("已复制字段值"));
            return;
        }
    }
    const auto selected = m_protocolTree->selectedItems();
    if (selected.isEmpty())
        return;
    auto *item = selected.constFirst();
    const QString value = item->data(0, FieldRole).toJsonObject().isEmpty() ? item->text(0) : item->text(2);
    QApplication::clipboard()->setText(value);
    m_statusText->setText(tr("已复制当前值"));
}

void MainWindow::copyCurrentPath()
{
    if (m_currentPath.isEmpty()) return;
    QApplication::clipboard()->setText(QDir::toNativeSeparators(m_currentPath));
    m_statusText->setText(tr("已复制文件完整路径"));
}

void MainWindow::jumpToOffset()
{
    if (m_currentPath.isEmpty()) return;
    bool accepted = false;
    const QString value = QInputDialog::getText(this, tr("跳转到 Offset"),
        tr("输入十进制或十六进制位置（例如 539 或 0x21B）"), QLineEdit::Normal, "0x0", &accepted).trimmed();
    if (!accepted || value.isEmpty()) return;
    bool ok = false;
    const qint64 offset = value.startsWith("0x", Qt::CaseInsensitive)
        ? value.mid(2).toLongLong(&ok, 16) : value.toLongLong(&ok, 10);
    const qint64 fileSize = QFileInfo(m_currentPath).size();
    if (!ok || offset < 0 || offset >= fileSize) {
        QMessageBox::warning(this, tr("Offset 无效"), tr("请输入 0 到 %1 之间的位置。").arg(qMax<qint64>(0, fileSize - 1)));
        return;
    }
    showHex(offset, 1);
    m_tabs->setCurrentWidget(m_hexPanel);
    m_statusText->setText(tr("已跳转到 Offset 0x%1").arg(offset, 0, 16).toUpper());
}

void MainWindow::addBookmark()
{
    if (m_currentPath.isEmpty()) return;
    bool accepted = false;
    const QString note = QInputDialog::getText(this, tr("添加 Offset 书签"), tr("备注"), QLineEdit::Normal,
                                                tr("关键位置"), &accepted).trimmed();
    if (!accepted) return;
    const qint64 offset = currentOffset();
    QString location;
    const auto selected = m_protocolTree->selectedItems();
    if (!selected.isEmpty()) location = selected.constFirst()->text(0);
    QJsonObject bookmark{{"offset", offset}, {"note", note.isEmpty() ? tr("关键位置") : note}, {"location", location}};
    m_bookmarks.append(bookmark);
    populateBookmarks();
    m_tabs->setCurrentWidget(m_bookmarksTable->parentWidget());
    m_bookmarksTable->selectRow(m_bookmarks.size() - 1);
    m_statusText->setText(tr("已添加书签：0x%1").arg(offset, 0, 16).toUpper());
}

void MainWindow::removeBookmark()
{
    const int row = m_bookmarksTable ? m_bookmarksTable->currentRow() : -1;
    if (row < 0 || row >= m_bookmarks.size()) return;
    m_bookmarks.removeAt(row);
    populateBookmarks();
    m_statusText->setText(tr("已删除书签"));
}

void MainWindow::onBookmarkActivated()
{
    const int row = m_bookmarksTable ? m_bookmarksTable->currentRow() : -1;
    if (row < 0 || row >= m_bookmarks.size()) return;
    const qint64 offset = jsonInteger(m_bookmarks.at(row).toObject().value("offset"));
    showHex(offset, 1);
    m_tabs->setCurrentWidget(m_hexPanel);
    m_statusText->setText(tr("书签定位到 Offset 0x%1").arg(offset, 0, 16).toUpper());
}

void MainWindow::exportHtml()
{
    if (m_currentPath.isEmpty())
        return;
    const auto path = QFileDialog::getSaveFileName(this, tr("导出 HTML 报告"), QDir(projectRoot()).filePath("tmp/AVScope-report.html"), "HTML (*.html)");
    if (!path.isEmpty())
        runExport("html", path);
}

void MainWindow::exportJson()
{
    if (m_currentPath.isEmpty())
        return;
    const auto path = QFileDialog::getSaveFileName(this, tr("导出 JSON 报告"), QDir(projectRoot()).filePath("tmp/AVScope-report.json"), "JSON (*.json)");
    if (!path.isEmpty())
        runExport("json", path);
}

void MainWindow::compareBinary() { runCompare("binary"); }
void MainWindow::compareProtocol() { runCompare("protocol"); }
void MainWindow::compareFrames() { runCompare("frames"); }

void MainWindow::runCompare(const QString &mode)
{
    if (m_currentPath.isEmpty()) {
        QMessageBox::information(this, tr("对比"), tr("请先打开左侧文件。"));
        return;
    }
    const QString configured = qEnvironmentVariable("AVSCOPE_COMPARE_PATH");
    const QString other = QFileInfo::exists(configured) ? configured
        : QFileDialog::getOpenFileName(this, tr("选择右侧对比文件"), QFileInfo(m_currentPath).absolutePath());
    if (other.isEmpty()) return;
    const QString command = mode == "binary" ? "compare-binary" : mode == "protocol" ? "compare-protocol" : "compare-frames";
    const QString output = projectRoot() + QString("/tmp/qt-runtime/compare-%1-%2.json")
        .arg(mode).arg(QCoreApplication::applicationPid());
    QFile::remove(output);
    m_taskOutputPath = output;
    m_taskMode = mode;
    m_taskOtherPath = other;
    m_statusText->setText(tr("正在执行%1对比...").arg(mode));
    startEngineTask("compare", {command, m_currentPath, other, "--json", output});
}

void MainWindow::populateCompare(const QString &mode, const QJsonDocument &document, const QString &otherPath)
{
    m_compareTree->clear();
    const auto root = document.object();
    if (mode == "binary") {
        m_hexCompare->setComparison(m_currentPath, otherPath,
                                    jsonInteger(root.value("left_size")),
                                    jsonInteger(root.value("right_size")),
                                    root.value("chunks").toArray());
        if (qEnvironmentVariableIntValue("AVSCOPE_HEX_COMPARE_NEXT") != 0)
            m_hexCompare->stepDifference(1);
        const QString statePath = qEnvironmentVariable("AVSCOPE_HEX_COMPARE_STATE");
        if (!statePath.isEmpty()) {
            QJsonObject state;
            state["left_path"] = m_currentPath;
            state["right_path"] = otherPath;
            state["left_size"] = jsonInteger(root.value("left_size"));
            state["right_size"] = jsonInteger(root.value("right_size"));
            state["difference_count"] = m_hexCompare->differenceCount();
            state["focus_offset"] = static_cast<double>(m_hexCompare->currentOffset());
            state["window_offset"] = static_cast<double>(m_hexCompare->windowOffset());
            state["synchronized_scrolling"] = m_hexCompare->synchronizedScrolling();
            QFile stateFile(statePath);
            QDir().mkpath(QFileInfo(statePath).absolutePath());
            if (stateFile.open(QIODevice::WriteOnly | QIODevice::Truncate))
                stateFile.write(QJsonDocument(state).toJson(QJsonDocument::Indented));
        }
    }
    auto *summary = new QTreeWidgetItem(m_compareTree);
    summary->setText(0, root.value("equal").toBool(false) ? tr("相同") : tr("已完成"));
    summary->setText(1, tr("%1  ↔  %2").arg(QFileInfo(m_currentPath).fileName(), QFileInfo(otherPath).fileName()));
    summary->setText(2, mode);

    if (mode == "binary") {
        summary->setText(3, formatSize(jsonInteger(root.value("left_size"))));
        summary->setText(4, formatSize(jsonInteger(root.value("right_size"))));
        for (const auto &value : root.value("chunks").toArray()) {
            const auto chunk = value.toObject();
            auto *item = new QTreeWidgetItem(summary);
            const qint64 offset = jsonInteger(chunk.value("offset"));
            item->setText(0, tr("变化"));
            item->setText(1, QString("0x%1").arg(offset, 0, 16).toUpper());
            item->setText(2, tr("32 字节窗口"));
            item->setText(3, chunk.value("left").toString());
            item->setText(4, chunk.value("right").toString());
            item->setData(0, OffsetRole, offset);
        }
    } else {
        for (const auto &sectionName : {QString("added"), QString("removed"), QString("changed")}) {
            const auto rows = root.value(sectionName).toArray();
            auto *section = new QTreeWidgetItem(summary);
            section->setText(0, sectionName.toUpper());
            section->setText(1, tr("%1 项").arg(rows.size()));
            const QColor color = sectionName == "added" ? QColor(m_dark ? "#73D2B3" : "#17785A")
                                 : sectionName == "removed" ? QColor(m_dark ? "#FF7B81" : "#B42318")
                                 : QColor(m_dark ? "#F5C567" : "#8A5A00");
            section->setForeground(0, color);
            for (const auto &value : rows) {
                const auto row = value.toObject();
                auto *item = new QTreeWidgetItem(section);
                item->setText(0, sectionName);
                item->setText(1, row.value("path").toString(QString("Frame #%1").arg(row.value("index").toInt())));
                const auto changes = row.value("changes").toObject();
                item->setText(2, changes.isEmpty() ? tr("对象") : tr("%1 项属性").arg(changes.size()));
                const qint64 offset = jsonInteger(row.value("offset"));
                item->setData(0, OffsetRole, offset > 0 ? offset : -1);
                for (int column = 0; column < item->columnCount(); ++column) item->setForeground(column, color);

                const auto addChanges = [&](auto &&self, QTreeWidgetItem *parent, const QJsonObject &object, const QString &prefix) -> void {
                    for (auto it = object.begin(); it != object.end(); ++it) {
                        const QString key = prefix.isEmpty() ? it.key() : prefix + "." + it.key();
                        const auto pair = it.value().toObject();
                        if (pair.contains("left") || pair.contains("right")) {
                            auto *detail = new QTreeWidgetItem(parent);
                            detail->setText(0, tr("变化"));
                            detail->setText(2, key);
                            const auto sideText = [](const QJsonValue &value) {
                                const auto object = value.toObject();
                                return object.contains("value") ? displayValue(object.value("value")) : displayValue(value);
                            };
                            detail->setText(3, sideText(pair.value("left")));
                            detail->setText(4, sideText(pair.value("right")));
                            detail->setToolTip(3, detail->text(3));
                            detail->setToolTip(4, detail->text(4));
                            for (int column = 0; column < detail->columnCount(); ++column) detail->setForeground(column, color);
                        } else if (!pair.isEmpty()) {
                            self(self, parent, pair, key);
                        }
                    }
                };
                addChanges(addChanges, item, changes, {});
            }
        }
    }
    m_compareTree->expandToDepth(2);
}

void MainWindow::saveProjectSnapshot()
{
    if (m_document.isNull() || m_currentPath.isEmpty()) return;
    const QString suggested = QDir(projectRoot()).filePath(QString("tmp/%1.avscope.json").arg(QFileInfo(m_currentPath).completeBaseName()));
    const QString path = QFileDialog::getSaveFileName(this, tr("保存工程快照"), suggested, tr("AVScope 工程 (*.avscope.json)"));
    if (path.isEmpty()) return;
    QJsonObject snapshot;
    snapshot["schema_version"] = 1;
    snapshot["saved_at"] = QDateTime::currentDateTime().toString(Qt::ISODate);
    snapshot["source_path"] = m_currentPath;
    snapshot["theme"] = m_dark ? "dark" : "light";
    snapshot["current_tab"] = m_tabs->currentIndex();
    snapshot["raw_options"] = QJsonArray::fromStringList(m_currentRawOptions);
    snapshot["bookmarks"] = m_bookmarks;
    snapshot["analysis"] = m_document.object();
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(snapshot).toJson(QJsonDocument::Indented)) < 0) {
        QMessageBox::critical(this, tr("保存失败"), file.errorString());
        return;
    }
    m_statusText->setText(tr("工程快照已保存：%1").arg(path));
    m_currentProjectPath = path;
}

void MainWindow::runExport(const QString &format, const QString &outputPath)
{
    m_taskOutputPath = outputPath;
    m_statusText->setText(tr("正在导出 %1 报告...").arg(format.toUpper()));
    QStringList arguments = {"analyze", m_currentPath, "--" + format, outputPath};
    arguments.append(m_currentRawOptions);
    startEngineTask("export", arguments);
}

void MainWindow::setDarkTheme() { applyTheme(true); }
void MainWindow::setLightTheme() { applyTheme(false); }

void MainWindow::applyTheme(bool dark, bool persist)
{
    m_dark = dark;
    if (persist) {
        m_settings.setValue("theme", dark ? "dark" : "light");
        m_settings.sync();
    }
    if (m_darkThemeAction) m_darkThemeAction->setChecked(dark);
    if (m_lightThemeAction) m_lightThemeAction->setChecked(!dark);
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
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { color: %4; background: %2; border: 1px solid %6; border-radius: 5px; padding: 7px 10px; selection-background-color: %7; selection-color: %8; }
        QComboBox::drop-down { border: 0; width: 22px; }
        QComboBox QAbstractItemView { color: %4; background: %2; border: 1px solid %6; selection-background-color: %7; selection-color: %8; }
        QCheckBox { color: %4; spacing: 5px; }
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
    m_protocolTree->setStyleSheet(QString(R"(
        QTreeWidget#protocolTree {
            alternate-background-color: %1;
            outline: 0;
        }
        QTreeWidget#protocolTree::item {
            min-height: 27px;
            padding: 3px 5px;
            border-bottom: 1px solid %2;
        }
        QTreeWidget#protocolTree::item:hover { background: %3; }
        QTreeWidget#protocolTree::item:selected { background: %4; color: %5; }
    )").arg(dark ? "#151F28" : "#F7F9FB",
             dark ? "#1C2833" : "#EEF2F5",
             hover, select, selectText));
    m_timeline->setDarkTheme(dark);
    m_hexCompare->setDarkTheme(dark);
    m_preview->setDarkTheme(dark);
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
        if (QFileInfo::exists(dir.filePath("avscope/cli.py"))
            || QFileInfo::exists(dir.filePath("AVScope/cli.py")))
            return dir.absolutePath();
        dir.cdUp();
    }
    return QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
}

QString MainWindow::pythonExecutable() const
{
    const auto env = qEnvironmentVariable("AVSCOPE_PYTHON");
    return env.isEmpty() ? QStringLiteral("python") : env;
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
    return projectRoot() + QString("/tmp/qt-runtime/current-analysis-%1.json")
        .arg(QCoreApplication::applicationPid());
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
