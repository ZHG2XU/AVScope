#include "HexCompareWidget.h"

#include <QCheckBox>
#include <QFile>
#include <QFileInfo>
#include <QFontDatabase>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QScrollBar>
#include <QSplitter>
#include <QTextBlock>
#include <QTextCursor>
#include <QVBoxLayout>

#include <algorithm>

namespace {
constexpr qint64 WindowBytes = 16 * 1024;
constexpr int BytesPerLine = 16;
constexpr int AddressChars = 14;
constexpr int AsciiStart = AddressChars + BytesPerLine * 3 + 2;

QByteArray readWindow(const QString &path, qint64 offset)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || !file.seek(offset))
        return {};
    return file.read(WindowBytes);
}

QString byteText(uchar value)
{
    return QString("%1").arg(value, 2, 16, QChar('0')).toUpper();
}
}

HexCompareWidget::HexCompareWidget(QWidget *parent) : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(8);

    auto *tools = new QHBoxLayout;
    m_summary = new QLabel(tr("尚未执行二进制对比"));
    m_summary->setObjectName("compareSummary");
    m_summary->setTextInteractionFlags(Qt::TextSelectableByMouse);
    tools->addWidget(m_summary, 1);

    m_previousDifference = new QPushButton(tr("上一差异"));
    m_previousDifference->setToolTip(tr("跳到上一处差异"));
    m_nextDifference = new QPushButton(tr("下一差异"));
    m_nextDifference->setToolTip(tr("跳到下一处差异"));
    m_previousPage = new QPushButton(tr("上一页"));
    m_previousPage->setToolTip(tr("向前浏览 16 KiB"));
    m_nextPage = new QPushButton(tr("下一页"));
    m_nextPage->setToolTip(tr("向后浏览 16 KiB"));
    m_offsetEdit = new QLineEdit;
    m_offsetEdit->setObjectName("compareOffset");
    m_offsetEdit->setPlaceholderText(tr("Offset，例如 0x100"));
    m_offsetEdit->setMaximumWidth(180);
    m_offsetEdit->setClearButtonEnabled(true);
    m_syncScroll = new QCheckBox(tr("同步滚动"));
    m_syncScroll->setChecked(true);
    tools->addWidget(m_previousDifference);
    tools->addWidget(m_nextDifference);
    tools->addWidget(m_previousPage);
    tools->addWidget(m_nextPage);
    tools->addWidget(m_offsetEdit);
    tools->addWidget(m_syncScroll);
    layout->addLayout(tools);

    auto *titles = new QHBoxLayout;
    m_leftTitle = new QLabel(tr("左侧文件"));
    m_rightTitle = new QLabel(tr("右侧文件"));
    m_leftTitle->setObjectName("compareFileTitle");
    m_rightTitle->setObjectName("compareFileTitle");
    m_leftTitle->setTextInteractionFlags(Qt::TextSelectableByMouse);
    m_rightTitle->setTextInteractionFlags(Qt::TextSelectableByMouse);
    titles->addWidget(m_leftTitle, 1);
    titles->addWidget(m_rightTitle, 1);
    layout->addLayout(titles);

    auto *splitter = new QSplitter(Qt::Horizontal);
    splitter->setChildrenCollapsible(false);
    m_leftView = new QPlainTextEdit;
    m_rightView = new QPlainTextEdit;
    for (auto *view : {m_leftView, m_rightView}) {
        view->setReadOnly(true);
        view->setLineWrapMode(QPlainTextEdit::NoWrap);
        view->setFont(QFontDatabase::systemFont(QFontDatabase::FixedFont));
        view->setTabChangesFocus(true);
        view->setCenterOnScroll(false);
    }
    m_leftView->setObjectName("leftHexCompare");
    m_rightView->setObjectName("rightHexCompare");
    splitter->addWidget(m_leftView);
    splitter->addWidget(m_rightView);
    splitter->setSizes({600, 600});
    layout->addWidget(splitter, 1);

    m_range = new QLabel(tr("可见范围 --"));
    m_range->setObjectName("sectionHint");
    layout->addWidget(m_range);

    connect(m_previousDifference, &QPushButton::clicked, this, [this] { navigateDifference(-1); });
    connect(m_nextDifference, &QPushButton::clicked, this, [this] { navigateDifference(1); });
    connect(m_previousPage, &QPushButton::clicked, this, [this] {
        loadWindow(qMax<qint64>(0, m_windowOffset - WindowBytes));
    });
    connect(m_nextPage, &QPushButton::clicked, this, [this] {
        const qint64 maximum = qMax(m_leftSize, m_rightSize);
        if (m_windowOffset + WindowBytes < maximum)
            loadWindow(m_windowOffset + WindowBytes);
    });
    connect(m_offsetEdit, &QLineEdit::returnPressed, this, [this] {
        bool ok = false;
        const qint64 offset = parseOffset(m_offsetEdit->text(), &ok);
        if (ok) loadWindow(offset, offset);
    });
    connect(m_leftView->verticalScrollBar(), &QScrollBar::valueChanged, this,
            [this](int value) { synchronizeScroll(m_leftView, m_rightView, value); });
    connect(m_rightView->verticalScrollBar(), &QScrollBar::valueChanged, this,
            [this](int value) { synchronizeScroll(m_rightView, m_leftView, value); });
    connect(m_leftView->horizontalScrollBar(), &QScrollBar::valueChanged, this,
            [this](int value) {
                if (m_syncScroll->isChecked() && !m_syncingScroll) {
                    m_syncingScroll = true;
                    m_rightView->horizontalScrollBar()->setValue(value);
                    m_syncingScroll = false;
                }
            });
    connect(m_rightView->horizontalScrollBar(), &QScrollBar::valueChanged, this,
            [this](int value) {
                if (m_syncScroll->isChecked() && !m_syncingScroll) {
                    m_syncingScroll = true;
                    m_leftView->horizontalScrollBar()->setValue(value);
                    m_syncingScroll = false;
                }
            });
}

void HexCompareWidget::setComparison(const QString &leftPath, const QString &rightPath,
                                     qint64 leftSize, qint64 rightSize, const QJsonArray &chunks)
{
    m_leftPath = leftPath;
    m_rightPath = rightPath;
    m_leftSize = leftSize;
    m_rightSize = rightSize;
    m_differenceOffsets.clear();
    for (const auto &value : chunks) {
        const qint64 offset = static_cast<qint64>(value.toObject().value("offset").toDouble());
        if (offset >= 0) m_differenceOffsets.push_back(offset);
    }
    std::sort(m_differenceOffsets.begin(), m_differenceOffsets.end());
    m_differenceOffsets.erase(std::unique(m_differenceOffsets.begin(), m_differenceOffsets.end()), m_differenceOffsets.end());
    m_currentDifference = m_differenceOffsets.isEmpty() ? -1 : 0;
    m_leftTitle->setText(tr("左侧  %1  ·  %2").arg(QFileInfo(leftPath).fileName(), formatSize(leftSize)));
    m_rightTitle->setText(tr("右侧  %1  ·  %2").arg(QFileInfo(rightPath).fileName(), formatSize(rightSize)));
    m_leftTitle->setToolTip(leftPath);
    m_rightTitle->setToolTip(rightPath);
    m_summary->setText(m_differenceOffsets.isEmpty()
        ? tr("文件内容相同  ·  %1 bytes").arg(qMax(leftSize, rightSize))
        : tr("发现 %1 个差异窗口  ·  大小变化 %2 bytes")
              .arg(m_differenceOffsets.size()).arg(rightSize - leftSize));
    m_previousDifference->setEnabled(!m_differenceOffsets.isEmpty());
    m_nextDifference->setEnabled(!m_differenceOffsets.isEmpty());
    const qint64 firstOffset = m_differenceOffsets.isEmpty() ? 0 : m_differenceOffsets.first();
    loadWindow(firstOffset, firstOffset);
}

void HexCompareWidget::loadWindow(qint64 offset, qint64 focusOffset)
{
    const qint64 maximum = qMax(m_leftSize, m_rightSize);
    if (maximum <= 0) {
        m_leftView->clear();
        m_rightView->clear();
        return;
    }
    offset = qBound<qint64>(0, offset, qMax<qint64>(0, maximum - 1));
    m_windowOffset = (offset / WindowBytes) * WindowBytes;
    m_focusOffset = focusOffset >= 0 ? focusOffset : offset;
    const QByteArray left = readWindow(m_leftPath, m_windowOffset);
    const QByteArray right = readWindow(m_rightPath, m_windowOffset);
    renderSide(m_leftView, left, right, m_leftSize, m_rightSize, true, focusOffset);
    renderSide(m_rightView, right, left, m_rightSize, m_leftSize, false, focusOffset);
    const qint64 end = qMin(maximum, m_windowOffset + WindowBytes);
    m_previousPage->setEnabled(m_windowOffset > 0);
    m_nextPage->setEnabled(end < maximum);
    m_range->setText(tr("可见范围  0x%1 - 0x%2  ·  每行 16 字节")
                         .arg(m_windowOffset, 0, 16).arg(qMax<qint64>(m_windowOffset, end - 1), 0, 16).toUpper());
    m_offsetEdit->setText(QString("0x%1").arg(focusOffset >= 0 ? focusOffset : m_windowOffset, 0, 16).toUpper());
}

bool HexCompareWidget::synchronizedScrolling() const
{
    return m_syncScroll->isChecked();
}

void HexCompareWidget::stepDifference(int direction)
{
    navigateDifference(direction);
}

void HexCompareWidget::renderSide(QPlainTextEdit *view, const QByteArray &own, const QByteArray &other,
                                  qint64 ownSize, qint64 otherSize, bool, qint64 focusOffset)
{
    const qint64 maximum = qMax(m_leftSize, m_rightSize);
    const int lineCount = static_cast<int>(qMin(WindowBytes, maximum - m_windowOffset) + BytesPerLine - 1) / BytesPerLine;
    QStringList lines;
    lines.reserve(lineCount);
    for (int line = 0; line < lineCount; ++line) {
        const qint64 base = m_windowOffset + line * BytesPerLine;
        QString text = QString("%1  ").arg(base, 12, 16, QChar('0')).toUpper();
        QString ascii;
        for (int column = 0; column < BytesPerLine; ++column) {
            const int local = line * BytesPerLine + column;
            const qint64 absolute = base + column;
            const bool ownPresent = absolute < ownSize && local < own.size();
            const bool otherPresent = absolute < otherSize && local < other.size();
            const uchar ownByte = ownPresent ? static_cast<uchar>(own.at(local)) : 0;
            const uchar otherByte = otherPresent ? static_cast<uchar>(other.at(local)) : 0;
            text += ownPresent ? byteText(ownByte) : QString("--");
            text += ' ';
            ascii += ownPresent && ownByte >= 32 && ownByte <= 126 ? QChar(ownByte) : ownPresent ? QChar('.') : QChar(' ');
        }
        lines << text + " |" + ascii + "|";
    }

    view->setPlainText(lines.join('\n'));
    QList<QTextEdit::ExtraSelection> selections;
    const QColor changedBackground = m_dark ? QColor("#7A3E18") : QColor("#FFD7A8");
    const QColor changedText = m_dark ? QColor("#FFF4E5") : QColor("#522500");
    const QColor missingBackground = m_dark ? QColor("#71313A") : QColor("#FFD1D5");
    const QColor missingText = m_dark ? QColor("#FFE8EA") : QColor("#65151D");
    const QColor focusBackground = m_dark ? QColor("#A75B12") : QColor("#FFB14A");
    for (int line = 0; line < lineCount; ++line) {
        const qint64 base = m_windowOffset + line * BytesPerLine;
        const QTextBlock block = view->document()->findBlockByNumber(line);
        for (int column = 0; column < BytesPerLine; ++column) {
            const int local = line * BytesPerLine + column;
            const qint64 absolute = base + column;
            const bool ownPresent = absolute < ownSize && local < own.size();
            const bool otherPresent = absolute < otherSize && local < other.size();
            const bool changed = ownPresent != otherPresent || (ownPresent && otherPresent && own.at(local) != other.at(local));
            if (!changed) continue;
            const QColor background = absolute == focusOffset ? focusBackground : ownPresent ? changedBackground : missingBackground;
            const QColor foreground = ownPresent ? changedText : missingText;
            for (const auto [start, length] : {qMakePair(AddressChars + column * 3, 2), qMakePair(AsciiStart + column, 1)}) {
                QTextEdit::ExtraSelection selection;
                selection.cursor = QTextCursor(block);
                selection.cursor.setPosition(block.position() + start);
                selection.cursor.movePosition(QTextCursor::Right, QTextCursor::KeepAnchor, length);
                selection.format.setBackground(background);
                selection.format.setForeground(foreground);
                selections.push_back(selection);
            }
        }
    }
    view->setExtraSelections(selections);
    if (focusOffset >= m_windowOffset && focusOffset < m_windowOffset + WindowBytes) {
        const int line = static_cast<int>((focusOffset - m_windowOffset) / BytesPerLine);
        QTextCursor cursor(view->document()->findBlockByNumber(line));
        view->setTextCursor(cursor);
        view->centerCursor();
    }
}

void HexCompareWidget::navigateDifference(int direction)
{
    if (m_differenceOffsets.isEmpty()) return;
    m_currentDifference = (m_currentDifference + direction + m_differenceOffsets.size()) % m_differenceOffsets.size();
    const qint64 offset = m_differenceOffsets.at(m_currentDifference);
    loadWindow(offset, offset);
    m_summary->setText(tr("差异 %1 / %2  ·  Offset 0x%3")
                           .arg(m_currentDifference + 1).arg(m_differenceOffsets.size()).arg(offset, 0, 16).toUpper());
}

void HexCompareWidget::synchronizeScroll(QPlainTextEdit *, QPlainTextEdit *target, int value)
{
    if (!m_syncScroll->isChecked() || m_syncingScroll) return;
    m_syncingScroll = true;
    target->verticalScrollBar()->setValue(value);
    m_syncingScroll = false;
}

qint64 HexCompareWidget::parseOffset(const QString &text, bool *ok) const
{
    QString value = text.trimmed();
    int base = 10;
    if (value.startsWith("0x", Qt::CaseInsensitive)) {
        value.remove(0, 2);
        base = 16;
    }
    return value.toLongLong(ok, base);
}

QString HexCompareWidget::formatSize(qint64 bytes) const
{
    if (bytes >= 1024 * 1024) return tr("%1 MiB").arg(bytes / 1048576.0, 0, 'f', 2);
    if (bytes >= 1024) return tr("%1 KiB").arg(bytes / 1024.0, 0, 'f', 1);
    return tr("%1 B").arg(bytes);
}

void HexCompareWidget::setDarkTheme(bool dark)
{
    m_dark = dark;
    if (!m_leftPath.isEmpty()) loadWindow(m_windowOffset, m_currentDifference >= 0 ? m_differenceOffsets.value(m_currentDifference, -1) : -1);
}
