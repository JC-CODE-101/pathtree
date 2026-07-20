import sys
import asyncio
from sqlmodel import Session
from pathtree.database.connection import create_db_engine, init_db
from pathtree.services.node_service import NodeService
from pathtree.database.repository import NodeRepository
from pathtree.ui.app import PathTreeApp

async def main():
    engine = create_db_engine(":memory:")
    init_db(engine)
    with Session(engine) as session:
        node_service = NodeService(NodeRepository(session))
        app = PathTreeApp(node_service=node_service)
        async with app.run_test(size=(80, 50)) as pilot:
            while app.screen.id != "main-screen":
                await pilot.pause(0.01)

            await pilot.press("a")
            await pilot.pause(0.01)

            dialog = app.screen
            await pilot.click("#radio-directory")
            await pilot.pause(0.1) # longer pause to ensure full layout

            name_input = dialog.query_one('#input-name')
            print(f"Name input size: {name_input.size}, height: {name_input.styles.height}")

            p_widget = dialog.query_one('#input-path-wrapper')
            print(f"PathAutocomplete wrapper size: {p_widget.size}, height: {p_widget.styles.height}")
            for child in p_widget.children:
                print(f"Child: {child!r}, visible: {child.visible}, display: {child.styles.display}, size: {child.size}, height style: {child.styles.height}")

if __name__ == "__main__":
    asyncio.run(main())
