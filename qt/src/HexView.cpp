#include "HexView.h"

#include <QApplication>
#include <QClipboard>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QTextBlock>
#include <QTextCursor>
#include <QTextEdit>

#include <utility>

HexView::HexView(QWidget *parent)
    : QPlainTextEdit(parent)
{
}

void HexView::clearColumnSelection()
{
    m_columnSelecting = false;
    m_column = Column::None;
    m_anchorLine = -1;
    m_anchorColumn = -1;
    m_columnSelectionText.clear();
    setExtraSelections({});
}

QString HexView::columnSelectionText() const
{
    return m_columnSelectionText;
}

void HexView::mousePressEvent(QMouseEvent *event)
{
    if (event->button() != Qt::LeftButton || event->modifiers().testFlag(Qt::ControlModifier)) {
        clearColumnSelection();
        QPlainTextEdit::mousePressEvent(event);
        return;
    }

    const QTextCursor cursor = cursorForPosition(event->position().toPoint());
    const Column column = columnAt(cursor.positionInBlock());
    if (column == Column::None) {
        clearColumnSelection();
        QPlainTextEdit::mousePressEvent(event);
        return;
    }

    clearColumnSelection();
    m_columnSelecting = true;
    m_column = column;
    m_anchorLine = cursor.blockNumber();
    const auto range = columnRange(column);
    m_anchorColumn = qBound(range.first, cursor.positionInBlock(), range.second);
    QTextCursor caret(cursor);
    caret.clearSelection();
    setTextCursor(caret);
    event->accept();
}

void HexView::mouseMoveEvent(QMouseEvent *event)
{
    if (!m_columnSelecting || !event->buttons().testFlag(Qt::LeftButton)) {
        QPlainTextEdit::mouseMoveEvent(event);
        return;
    }
    updateColumnSelection(event->position().toPoint());
    event->accept();
}

void HexView::mouseReleaseEvent(QMouseEvent *event)
{
    if (!m_columnSelecting || event->button() != Qt::LeftButton) {
        QPlainTextEdit::mouseReleaseEvent(event);
        return;
    }
    updateColumnSelection(event->position().toPoint());
    m_columnSelecting = false;
    event->accept();
}

void HexView::keyPressEvent(QKeyEvent *event)
{
    if (event->matches(QKeySequence::Copy) && !m_columnSelectionText.isEmpty()) {
        QApplication::clipboard()->setText(m_columnSelectionText);
        event->accept();
        return;
    }
    if (event->key() == Qt::Key_Escape && !m_columnSelectionText.isEmpty()) {
        clearColumnSelection();
        event->accept();
        return;
    }
    QPlainTextEdit::keyPressEvent(event);
}

HexView::Column HexView::columnAt(int positionInBlock)
{
    if (positionInBlock >= 0 && positionInBlock < 12)
        return Column::Offset;
    if (positionInBlock >= 14 && positionInBlock <= 61)
        return Column::Hex;
    if (positionInBlock >= 64 && positionInBlock <= 80)
        return Column::Ascii;
    return Column::None;
}

QPair<int, int> HexView::columnRange(Column column)
{
    switch (column) {
    case Column::Offset:
        return {0, 12};
    case Column::Hex:
        return {14, 61};
    case Column::Ascii:
        return {64, 80};
    case Column::None:
        break;
    }
    return {0, 0};
}

void HexView::updateColumnSelection(const QPoint &position)
{
    const QTextCursor current = cursorForPosition(position);
    const auto range = columnRange(m_column);
    int currentLine = current.blockNumber();
    int currentColumn = qBound(range.first, current.positionInBlock(), range.second);

    int startLine = m_anchorLine;
    int startColumn = m_anchorColumn;
    int endLine = currentLine;
    int endColumn = currentColumn;
    if (startLine > endLine || (startLine == endLine && startColumn > endColumn)) {
        std::swap(startLine, endLine);
        std::swap(startColumn, endColumn);
    }

    QList<QTextEdit::ExtraSelection> selections;
    QStringList selectedLines;
    for (int line = startLine; line <= endLine; ++line) {
        const QTextBlock block = document()->findBlockByLineNumber(line);
        if (!block.isValid())
            continue;
        const int from = line == startLine ? startColumn : range.first;
        const int to = line == endLine ? endColumn : range.second;
        if (to <= from)
            continue;

        QTextEdit::ExtraSelection selection;
        selection.cursor = QTextCursor(block);
        selection.cursor.setPosition(block.position() + from);
        selection.cursor.setPosition(block.position() + qMin(to, block.length() - 1), QTextCursor::KeepAnchor);
        selection.format.setBackground(palette().highlight());
        selection.format.setForeground(palette().highlightedText());
        selections.append(selection);
        selectedLines.append(block.text().mid(from, to - from));
    }
    setExtraSelections(selections);
    m_columnSelectionText = selectedLines.join('\n');
}
