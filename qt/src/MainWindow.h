#pragma once

#include <QJsonDocument>
#include <QMainWindow>
#include <QProcess>

class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QPushButton;
class QStackedWidget;
class QTableWidget;
class QTabWidget;
class QTreeWidget;
class QTreeWidgetItem;
class TimelineWidget;

class MainWindow final : public QMainWindow
{
    Q_OBJECT
public:
    explicit MainWindow(QWidget *parent = nullptr);
    void openPath(const QString &path);

protected:
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;

private slots:
    void chooseFile();
    void reloadCurrent();
    void analysisFinished(int exitCode, QProcess::ExitStatus status);
    void onTreeSelectionChanged();
    void onFieldSelectionChanged();
    void searchNext();
    void exportHtml();
    void exportJson();
    void setDarkTheme();
    void setLightTheme();

private:
    void buildUi();
    void buildMenus();
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
    void showHex(qint64 offset, qint64 size = 1);
    void runExport(const QString &format, const QString &outputPath);
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
    QString m_currentPath;
    QJsonDocument m_document;
    QProcess *m_process = nullptr;
    QTreeWidget *m_protocolTree = nullptr;
    QTableWidget *m_fieldsTable = nullptr;
    QTableWidget *m_framesTable = nullptr;
    QPlainTextEdit *m_hexView = nullptr;
    QPlainTextEdit *m_preview = nullptr;
    QPlainTextEdit *m_diagnostics = nullptr;
    QPlainTextEdit *m_log = nullptr;
    QTabWidget *m_tabs = nullptr;
    TimelineWidget *m_timeline = nullptr;
    QLineEdit *m_search = nullptr;
    QLabel *m_fileLabel = nullptr;
    QLabel *m_formatMetric = nullptr;
    QLabel *m_sizeMetric = nullptr;
    QLabel *m_nodeMetric = nullptr;
    QLabel *m_issueMetric = nullptr;
    QLabel *m_statusText = nullptr;
    QPushButton *m_darkButton = nullptr;
    QPushButton *m_lightButton = nullptr;
};
