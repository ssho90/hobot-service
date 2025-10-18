import os

# Graphviz 실행 경로 지정
os.environ["PATH"] = r"C:\Program Files\Graphviz\bin" + os.pathsep + os.environ["PATH"]

# main.py
# main.py
from diagrams import Diagram, Cluster, Edge

# 사용자께서 제공해주신 목록을 기준으로 검증 및 수정한 패키지 경로입니다.
# --------------------------------------------------------------------------
# Analytics
from diagrams.aws.analytics import Athena

# Compute
from diagrams.aws.compute import EC2, Fargate
from diagrams.aws.compute import EC2ContainerRegistry as ECR # ECR은 compute에 속하며, Alias를 사용

# Management & Governance
from diagrams.aws.management import AutoScaling # AutoScaling은 management에 속합니다.
from diagrams.aws.management import Cloudtrail, Cloudwatch

# Migration & Transfer
from diagrams.aws.migration import Datasync, TransferForSftp # DataSync는 migration에 속합니다.

# Network & Content Delivery
from diagrams.aws.network import ELB, Route53, VPC, Privatelink, InternetGateway, NATGateway

# Security, Identity, & Compliance
from diagrams.aws.security import KMS, Shield, CertificateManager, Guardduty
from diagrams.aws.security import WAF # WAF는 security에 속합니다.

# Storage
from diagrams.aws.storage import S3, EFS

# On-Premise (사용자 아이콘)
from diagrams.onprem.client import Users, Client
# --------------------------------------------------------------------------


# 다이어그램 설정
with Diagram("AWS Architecture (Corrected Packages)", show=False, filename="aws_architecture_final", direction="TB"):

    # 외부 사용자 및 디바이스
    with Cluster(""):
        user_group = Users("users")
        sftp_ingestion = user_group >> Edge(label="SFTP File Ingestion", style="dashed")
        s3_ingestion = user_group >> Edge(label="S3 File Ingestion", style="dashed")

    # AWS 클라우드 전체 영역
    with Cluster("AWS Cloud"):

        # 리전 외부의 글로벌 서비스
        with Cluster(""):
            aws_services_top = [
                Privatelink("AWS PrivateLink"),
                Cloudtrail("Amazon CloudTrail"),
                KMS("AWS Key Management Service"),
                Shield("AWS Shield"),
            ]

        # 리전 영역
        with Cluster("Region"):

            # VPC 외부의 리전 서비스
            region_services = [
                Route53("Amazon Route 53"),
                CertificateManager("Amazon Certificate Manager"),
                Guardduty("Amazon GuardDuty"),
                Cloudwatch("Amazon Cloudwatch"),
                ECR("Amazon ECR")
            ]

            # VPC 영역
            with Cluster("VPC"):
                igw = InternetGateway("Internet Gateway")

                # 중앙 데이터 서비스
                with Cluster(""):
                    transfer_family = TransferForSftp("AWS Transfer Family")
                    s3 = S3("Amazon S3")
                    datasync = Datasync("AWS DataSync")
                    athena = Athena("Amazon Athena")
                    efs = EFS("Amazon EFS")

                # 가용 영역 A
                with Cluster("Availability Zone A"):
                    with Cluster("Public subnet A"):
                        waf = WAF("AWS WAF")
                        elb = ELB("Amazon ELB Shiny ELB RStudio")
                        nat_a = NATGateway("NAT Gateway")

                    with Cluster("Private subnet A"):
                        ec2_rstudio_a = EC2("Amazon EC5")
                        fargate_shiny_a = [Fargate("AWS Fargate\nShiny"), Fargate("AWS Fargate\nShiny")]

                        with Cluster("Auto Scaling group"):
                            # AutoScaling은 management에서 임포트
                            asg_a = AutoScaling("")
                            ec2_server_a = EC2("EC2 Server")
                            # ECR은 compute에서 임포트
                            rstudio_containers_a = ECR("RStudio\nContainers")
                            asg_a - [ec2_server_a, rstudio_containers_a]

                # 가용 영역 B
                with Cluster("Availability Zone B"):
                    with Cluster("Public subnet B"):
                        nat_b = NATGateway("NAT Gateway")

                    with Cluster("Private subnet B"):
                        ec2_rstudio_b = EC2("Amazon EC5")
                        fargate_shiny_b = [Fargate("AWS Fargate\nShiny"), Fargate("AWS Fargate\nShiny")]

                        with Cluster("Auto Scaling group"):
                            asg_b = AutoScaling("")
                            ec2_server_b = EC2("EC2 Server")
                            rstudio_containers_b = ECR("RStudio\nContainers")
                            asg_b - [ec2_server_b, rstudio_containers_b]


    # --- 연결 관계 정의 (생략, 이전 코드와 동일) ---
    # 편의상 연결 관계 코드는 생략하지만, 실제 실행 시에는 포함해야 합니다.
    # User -> Route53 -> WAF -> ELB
    user_group >> Edge(label="1") >> region_services[0] >> Edge(label="2") >> waf >> Edge(label="3") >> elb
    igw >> nat_a

    # Data Flow
    sftp_ingestion >> transfer_family >> Edge(label="8") >> s3 >> Edge(label="9") >> datasync >> Edge(label="10") >> efs
    s3 >> Edge(label="11") >> athena
    s3_ingestion >> s3

    # AZ A
    elb >> Edge(label="4\nRstudio traffic") >> ec2_rstudio_a
    elb >> Edge(label="5\nShiny traffic") >> fargate_shiny_a[0]
    elb >> Edge(label="Rstudio traffic") >> asg_a
    rstudio_containers_a >> Edge(label="Egress\nFiltering") >> athena
    ec2_server_a >> Edge(label="JDBC") >> athena
    fargate_shiny_a >> Edge(label="NFS Mount", style="dashed") >> efs
    asg_a >> Edge(label="NFS Mount", style="dashed") >> efs

    # AZ B
    elb >> Edge(label="Rstudio traffic") >> ec2_rstudio_b
    elb >> Edge(label="Shiny traffic") >> fargate_shiny_b[0]
    elb >> Edge(label="Rstudio traffic") >> asg_b
    rstudio_containers_b >> Edge(label="Egress\nFiltering") >> athena
    ec2_server_b >> Edge(label="JDBC") >> athena
    fargate_shiny_b >> Edge(label="NFS Mount", style="dashed") >> efs
    asg_b >> Edge(label="NFS Mount", style="dashed") >> efs