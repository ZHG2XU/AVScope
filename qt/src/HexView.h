#pragma once

#include <QPlainTextEdit>

class QMouseEvent;
class QKeyEvent;

class HexView final : public QPlainTextEdit
{
    Q_OBJECT
public:
    explicit HexView(QWidget *parent = nullptr);

    void clearColumnSelection();
    QString columnSelectionText() const;

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void keyPressEvent(QKeyEvent *event) override;

private:
    enum class Column { None, Offset, Hex, Ascii };

    static Column columnAt(int positionInBlock);
    static QPair<int, int> columnRange(Column column);
    void updateColumnSelection(const QPoint &position);

    bool m_columnSelecting = false;
    Column m_column = Column::None;
    int m_anchorLine = -1;
    int m_anchorColumn = -1;
    QString m_columnSelectionText;
};
