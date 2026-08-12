#pragma once

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMainWindow>
#include <QProcess>
#include <QSettings>

class QLabel;
class QCheckBox;
class QComboBox;
class QLineEdit;
class QMenu;
class QPlainTextEdit;
class QProgressBar;
class QPushButton;
class QSplitter;
class QTableWidget;
class QTabWidget;
class QTreeWidget;
class QTreeWidgetItem;
class TimelineWidget;
class MediaPreviewWidget;

class MainWindow final : public QMainWindow
{
    Q_OBJECT
public:
    explicit MainWindow(QWidget *parent = nullptr);
    void openPath(const QString &path);

protected:
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;
    void closeEvent(QCloseEvent *event) override;

private slots:
    void chooseFile();
    void reloadCurrent();
    void cancelAnalysis();
    void analysisFinished(int exitCode, QProcess::ExitStatus status);
    void onTreeSelectionChanged();
    void onFieldSelectionChanged();
    void onFrameSelectionChanged();
    void onDiagnosticSelectionChanged();
    void filterDiagnostics();
    void searchNext();
    void filterProtocolTree();
    void copyCurrentOffset();
    void copyCurrentValue();
    void copyCurrentPath();
    void jumpToOffset();
    void addBookmark();
    void removeBookmark();
    void onBookmarkActivated();
    void exportHtml();
    void exportJson();
    void compareBinary();
    void compareProtocol();
    void compareFrames();
    void saveProjectSnapshot();
    void stepMediaPreview(int direction);
    void setDarkTheme();
    void setLightTheme();

private:
    void buildUi();
    void buildMenus();
    void buildShortcuts();
    QWidget *buildHeader();
    QWidget *buildSummaryStrip();
    QWidget *buildProtocolPanel();
    QWidget *buildWorkspace();
    QWidget *buildInspector();
    QWidget *makeMetricCard(const QString &label, QLabel **valueLabel, const QString &accent);
    void applyTheme(bool dark);
    void loadDocument(const QJsonDocument &document);
    bool loadProjectSnapshot(const QString &path);
    void populateProtocolTree(const QJsonObject &node, QTreeWidgetItem *parent = nullptr);
    void populateFields(const QJsonObject &node);
    void populateFrames(const QJsonArray &frames);
    void populateStreams(const QJsonArray &streams);
    void populateTransportSessions(const QJsonObject &transport);
    void populateRtpVideo(const QJsonObject &video);
    void populateSipSdp(const QJsonObject &signaling);
    void populateRtcpFeedback(const QJsonObject &rtcp);
    void populateRtpTiming(const QJsonObject &transport);
    void populateTwcc(const QJsonObject &rtcp);
    void populateCodecHealth(const QJsonObject &health);
    void filterTransportSessions();
    void populateBookmarks();
    void populateDiagnostics(const QJsonArray &diagnostics, const QJsonObject &media);
    void filterDiagnostics(const QString &formatName);
    void showSelectionDetails(const QJsonObject &node, const QJsonObject &field = {});
    void showHex(qint64 offset, qint64 size = 1);
    void setAnalysisBusy(bool busy);
    void addRecentFile(const QString &path);
    void rebuildRecentMenu();
    void restoreWorkspaceState();
    bool filterTreeItem(QTreeWidgetItem *item, const QString &query, bool issuesOnly);
    void runExport(const QString &format, const QString &outputPath);
    void startEngineTask(const QString &kind, const QStringList &arguments);
    void runCompare(const QString &mode);
    void populateCompare(const QString &mode, const QJsonDocument &document, const QString &otherPath);
    QStringList rawOptionsForPath(const QString &path, bool *accepted);
    QString projectRoot() const;
    QString pythonExecutable() const;
    QString engineExecutable() const;
    QStringList engineArguments(const QStringList &arguments) const;
    QString analysisOutputPath() const;
    QColor fieldColor(const QJsonValue &value, const QString &hex, const QString &severity) const;
    static QString displayValue(const QJsonValue &value);
    static qint64 jsonInteger(const QJsonValue &value);
    static QString formatSize(qint64 bytes);
    static int countNodes(const QJsonObject &node);
    static int countFields(const QJsonObject &node);
    qint64 currentOffset() const;

    bool m_dark = true;
    bool m_cancelRequested = false;
    bool m_autoCompareTriggered = false;
    bool m_autoPreviewTriggered = false;
    QString m_taskKind;
    QString m_taskOutputPath;
    QString m_taskMode;
    QString m_taskOtherPath;
    QString m_currentPath;
    QString m_currentProjectPath;
    QStringList m_currentRawOptions;
    double m_previewPosition = 0.0;
    int m_previewFrame = 0;
    qint64 m_hexOffset = 0;
    QJsonDocument m_document;
    QProcess *m_process = nullptr;
    QSettings m_settings;
    QSplitter *m_mainSplitter = nullptr;
    QTreeWidget *m_protocolTree = nullptr;
    QTableWidget *m_fieldsTable = nullptr;
    QTableWidget *m_framesTable = nullptr;
    QTableWidget *m_streamsTable = nullptr;
    QTableWidget *m_transportSessionsTable = nullptr;
    QTableWidget *m_rtpVideoStreamsTable = nullptr;
    QTableWidget *m_rtpVideoIssuesTable = nullptr;
    QTableWidget *m_sipMessagesTable = nullptr;
    QTableWidget *m_sdpMappingsTable = nullptr;
    QTableWidget *m_rtcpFeedbackTable = nullptr;
    QTableWidget *m_rtcpMetadataTable = nullptr;
    QTableWidget *m_rtpTimingTable = nullptr;
    QTableWidget *m_rtpTimingEventsTable = nullptr;
    QTableWidget *m_twccFeedbackTable = nullptr;
    QTableWidget *m_twccPacketsTable = nullptr;
    QTabWidget *m_transportDetails = nullptr;
    QTableWidget *m_codecIssuesTable = nullptr;
    QTableWidget *m_codecParametersTable = nullptr;
    QTableWidget *m_codecResolutionsTable = nullptr;
    QTableWidget *m_bookmarksTable = nullptr;
    QTreeWidget *m_compareTree = nullptr;
    QPlainTextEdit *m_hexView = nullptr;
    MediaPreviewWidget *m_preview = nullptr;
    QTableWidget *m_diagnosticsTable = nullptr;
    QComboBox *m_diagnosticSeverityFilter = nullptr;
    QComboBox *m_diagnosticSourceFilter = nullptr;
    QCheckBox *m_diagnosticOffsetOnly = nullptr;
    QCheckBox *m_transportIssuesOnly = nullptr;
    QLabel *m_diagnosticSummary = nullptr;
    QLabel *m_transportSummary = nullptr;
    QLabel *m_rtpVideoSummary = nullptr;
    QLabel *m_sipSdpSummary = nullptr;
    QLabel *m_rtcpFeedbackSummary = nullptr;
    QLabel *m_rtpTimingSummary = nullptr;
    QLabel *m_twccSummary = nullptr;
    QLabel *m_codecMetric = nullptr;
    QLabel *m_codecStatusMetric = nullptr;
    QLabel *m_codecParameterMetric = nullptr;
    QLabel *m_codecSliceMetric = nullptr;
    QLabel *m_codecIssueMetric = nullptr;
    QLabel *m_codecResolutionMetric = nullptr;
    QPlainTextEdit *m_selectionDetails = nullptr;
    QPlainTextEdit *m_log = nullptr;
    QTabWidget *m_tabs = nullptr;
    TimelineWidget *m_timeline = nullptr;
    QLineEdit *m_search = nullptr;
    QCheckBox *m_issueFilter = nullptr;
    QMenu *m_recentMenu = nullptr;
    QProgressBar *m_progress = nullptr;
    QLabel *m_fileLabel = nullptr;
    QLabel *m_formatMetric = nullptr;
    QLabel *m_sizeMetric = nullptr;
    QLabel *m_nodeMetric = nullptr;
    QLabel *m_issueMetric = nullptr;
    QLabel *m_statusText = nullptr;
    QPushButton *m_darkButton = nullptr;
    QPushButton *m_lightButton = nullptr;
    QPushButton *m_cancelButton = nullptr;
    QJsonArray m_bookmarks;
    QJsonArray m_diagnostics;
};
