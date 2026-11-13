
import asyncio

from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function


class DemoPlugin:

    @kernel_function(description="Test Semantic Kernel function")
    def test_function(self) -> str:
        return "Semantic Kernel function executed successfully"


async def main():

    kernel = Kernel()

    kernel.add_plugin(
        DemoPlugin(),
        plugin_name="FarmAgents"
    )

    print("Registered plugins:", list(kernel.plugins.keys()))

    function = kernel.plugins["FarmAgents"]["test_function"]

    result = await kernel.invoke(function=function)

    print("Invocation result:", result.value)


if __name__ == "__main__":
    asyncio.run(main())
