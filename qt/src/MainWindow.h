#pragma once

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
    void searchNext();
    void filterProtocolTree();
    void copyCurrentOffset();
    void copyCurrentValue();
    void exportHtml();
    void exportJson();
    void compareBinary();
    void compareProtocol();
    void compareFrames();
    void saveProjectSnapshot();
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
    void populateProtocolTree(const QJsonObject &node, QTreeWidgetItem *parent = nullptr);
    void populateFields(const QJsonObject &node);
    void populateFrames(const QJsonArray &frames);
    void populateDiagnostics(const QJsonArray &diagnostics, const QJsonObject &media);
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

    bool m_dark = true;
    bool m_cancelRequested = false;
    bool m_autoCompareTriggered = false;
    QString m_taskKind;
    QString m_taskOutputPath;
    QString m_taskMode;
    QString m_taskOtherPath;
    QString m_currentPath;
    QStringList m_currentRawOptions;
    QJsonDocument m_document;
    QProcess *m_process = nullptr;
    QSettings m_settings;
    QSplitter *m_mainSplitter = nullptr;
    QTreeWidget *m_protocolTree = nullptr;
    QTableWidget *m_fieldsTable = nullptr;
    QTableWidget *m_framesTable = nullptr;
    QTreeWidget *m_compareTree = nullptr;
    QPlainTextEdit *m_hexView = nullptr;
    MediaPreviewWidget *m_preview = nullptr;
    QTableWidget *m_diagnosticsTable = nullptr;
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
};
