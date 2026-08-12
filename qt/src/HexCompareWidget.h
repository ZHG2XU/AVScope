#pragma once

#include <QJsonArray>
#include <QWidget>

class QCheckBox;
class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QPushButton;

class HexCompareWidget final : public QWidget
{
    Q_OBJECT
public:
    explicit HexCompareWidget(QWidget *parent = nullptr);

    void setComparison(const QString &leftPath, const QString &rightPath,
                       qint64 leftSize, qint64 rightSize, const QJsonArray &chunks);
    void setDarkTheme(bool dark);

    qint64 currentOffset() const { return m_focusOffset; }
    qint64 windowOffset() const { return m_windowOffset; }
    int differenceCount() const { return m_differenceOffsets.size(); }
    bool synchronizedScrolling() const;
    void stepDifference(int direction);

private:
    void loadWindow(qint64 offset, qint64 focusOffset = -1);
    void renderSide(QPlainTextEdit *view, const QByteArray &own, const QByteArray &other,
                    qint64 ownSize, qint64 otherSize, bool leftSide, qint64 focusOffset);
    void navigateDifference(int direction);
    void synchronizeScroll(QPlainTextEdit *source, QPlainTextEdit *target, int value);
    qint64 parseOffset(const QString &text, bool *ok) const;
    QString formatSize(qint64 bytes) const;

    QString m_leftPath;
    QString m_rightPath;
    qint64 m_leftSize = 0;
    qint64 m_rightSize = 0;
    qint64 m_windowOffset = 0;
    qint64 m_focusOffset = 0;
    QVector<qint64> m_differenceOffsets;
    int m_currentDifference = -1;
    bool m_dark = true;
    bool m_syncingScroll = false;

    QLabel *m_summary = nullptr;
    QLabel *m_leftTitle = nullptr;
    QLabel *m_rightTitle = nullptr;
    QLabel *m_range = nullptr;
    QLineEdit *m_offsetEdit = nullptr;
    QPushButton *m_previousDifference = nullptr;
    QPushButton *m_nextDifference = nullptr;
    QPushButton *m_previousPage = nullptr;
    QPushButton *m_nextPage = nullptr;
    QCheckBox *m_syncScroll = nullptr;
    QPlainTextEdit *m_leftView = nullptr;
    QPlainTextEdit *m_rightView = nullptr;
};
